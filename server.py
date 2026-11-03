import os
import sys
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Body, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

current_dir = Path(__file__).parent.resolve()
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from models import CandidateProfile, GeneratedApplication, ApplicationStatus, SearchConfig, AuditActionType
from storage import StorageManager, _get_target_dict, _get_matching_dict, normalize_status
from graph import build_pfe_agent_graph
from agents.searcher import generate_automated_search_targets
from agents.browser_automation import browser_agent
from agents.verifier import verification_agent
from agents.cv_parser import parse_pdf_cv_bytes
from agents.github_connector import sync_github_projects
from agents.linkedin_connector import crawl_linkedin_feed
from agents.email_connector import scan_inbox_emails, send_real_email_smtp
from agents.jobboard_connector import crawl_abg_jobboard
from agents.tailor_agent import personalize_application
from scheduler import scheduler_service

app = FastAPI(title="AI Job Application Agent API", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SAMPLE_LINKEDIN_POST = """📢 #RECRUTEMENT #STAGE_PFE 2027

Nous recherchons pour nos équipes plusieurs profils stagiaires PFE :
1. Capgemini Engineering (Casablanca / Rabat) :
Stagiaire Data Engineer & IA / LLM. Stack : Apache Spark, Kafka, FastAPI, Qdrant, RAG, Docker.
Envoyez vos CV à : recruitment.maroc@capgemini.com (Réf : PFE-DATA-IA-2027)

2. Devoteam Digital :
Recherche Stagiaires PFE Data Platform & ETL. Stack : Apache Airflow, dbt, MinIO, PostgreSQL, Power BI.
Contact RH : fatima.zahra.rh@devoteam.com

3. Startup FinTech X :
Recherche un(e) élève ingénieur(e) pour concevoir un pipeline de streaming temps réel et monitoring.
Contactez directement notre CTO à : tech-lead@fintech-x.io
"""

class AnalyzeRequest(BaseModel):
    raw_text: str
    min_score_threshold: Optional[int] = 50

class UpdateApplicationRequest(BaseModel):
    subject_line: Optional[str] = None
    email_body: Optional[str] = None
    cover_letter_snippet: Optional[str] = None
    status: Optional[str] = None
    applied_at: Optional[str] = None
    notes: Optional[str] = None
    contact_email: Optional[str] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    source_url: Optional[str] = None
    start_date: Optional[str] = None

static_dir = current_dir / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.on_event("startup")
def startup_event():
    scheduler_service.start()
    StorageManager.add_audit_log(
        agent_name="System",
        action=AuditActionType.SEARCH,
        description="Serveur Agent IA connecté aux comptes réels démarré."
    )

@app.get("/")
async def root():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "AI Job Application Agent API Active."}

@app.get("/api/stats")
async def get_stats():
    return StorageManager.get_stats()

@app.get("/api/search-config")
async def get_search_config():
    return StorageManager.get_search_config().model_dump()

@app.post("/api/search-config")
async def update_search_config(config_data: Dict[str, Any]):
    try:
        cfg = SearchConfig(**config_data)
        StorageManager.save_search_config(cfg)
        StorageManager.add_audit_log(
            agent_name="UserInterface",
            action=AuditActionType.APPROVAL,
            description="Configuration de veille autonome mise à jour."
        )
        return {"success": True, "config": cfg.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Configuration invalide : {str(e)}")

@app.get("/api/audit-logs")
async def get_audit_logs():
    logs = StorageManager.get_audit_logs()
    return [l.model_dump() for l in logs]

@app.get("/api/episodic-memory")
async def get_episodic_memory():
    memory = StorageManager.get_episodic_memory()
    return [m.model_dump() for m in memory]

# PDF CV UPLOAD & AUTO PARSING
@app.post("/api/upload-cv-pdf")
def upload_cv_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers PDF sont acceptés")
        
    contents = file.file.read()
    
    # Enregistrer le fichier sur disque pour les pièces jointes d'e-mail
    uploads_dir = current_dir / "uploads"
    uploads_dir.mkdir(exist_ok=True)
    cv_path = uploads_dir / "cv_yousra_khallou.pdf"
    with open(cv_path, "wb") as f:
        f.write(contents)

    try:
        parsed_profile = parse_pdf_cv_bytes(contents)
        StorageManager.save_profile(parsed_profile)
        StorageManager.add_audit_log(
            agent_name="CVParserAgent",
            action=AuditActionType.EXTRACTION,
            description=f"CV PDF '{file.filename}' analysé et sauvegardé pour les candidatures directes. Profil mis à jour pour {parsed_profile.full_name}."
        )
        return {"success": True, "filename": file.filename, "cv_saved": True, "profile": parsed_profile.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'analyse du CV PDF : {str(e)}")

# GITHUB SYNC
@app.post("/api/github-sync")
def sync_github(payload: Dict[str, str] = Body(default={"username": "yousra-khallou"})):
    username = payload.get("username", "yousra-khallou")
    projects = sync_github_projects(username)
    
    if not projects:
        raise HTTPException(status_code=404, detail=f"Aucun projet GitHub récupéré pour {username}")
        
    profile = StorageManager.get_profile()
    profile.top_projects = projects
    StorageManager.save_profile(profile)
    
    StorageManager.add_audit_log(
        agent_name="GitHubSyncAgent",
        action=AuditActionType.RESEARCH,
        description=f"Synchronisation GitHub effectuée : {len(projects)} dépôts importés depuis @{username}."
    )
    return {"success": True, "username": username, "projects_count": len(projects), "projects": [p.model_dump() for p in projects]}

# LIVE MULTI-CONNECTORS SCAN
@app.post("/api/connectors/scan-all")
def scan_all_connectors():
    config = StorageManager.get_search_config()
    StorageManager.add_audit_log(
        agent_name="MultiConnectorsAgent",
        action=AuditActionType.SEARCH,
        description="Veille multi-sources lancée : Scan LinkedIn Live + Gmail Inbox + ABG Job Board."
    )
    
    linkedin_targets = crawl_linkedin_feed(config.keywords)
    email_targets = scan_inbox_emails()
    abg_targets = crawl_abg_jobboard()
    
    all_targets = linkedin_targets + email_targets + abg_targets
    
    if not all_targets:
        return {"success": True, "targets_found": 0, "added_count": 0}
        
    profile = StorageManager.get_profile()
    langgraph_app = build_pfe_agent_graph()
    
    raw_text_sim = "\n\n".join([
        f"Entreprise : {t.company_name} ({t.location})\nPoste : {t.job_title}\nEmail : {t.contact_email}\nTechnos : {', '.join(t.technologies_mentioned)}\nContexte : {t.raw_context}"
        for t in all_targets
    ])
    
    initial_state = {
        "raw_input_text": raw_text_sim,
        "profile": profile,
        "min_score_threshold": config.min_match_score,
        "extracted_targets": all_targets,
        "company_researches": {},
        "match_results": [],
        "applications": [],
        "error": ""
    }
    
    final_state = langgraph_app.invoke(initial_state)
    generated_apps = final_state.get("applications", [])
    added = StorageManager.add_applications(generated_apps)
    
    return {
        "success": True,
        "targets_found": len(all_targets),
        "linkedin_count": len(linkedin_targets),
        "email_count": len(email_targets),
        "abg_count": len(abg_targets),
        "added_count": len(added),
        "added_applications": [a.model_dump() for a in added]
    }

@app.post("/api/trigger-scan")
def trigger_scan():
    return scan_all_connectors()

@app.get("/api/applications")
async def get_applications(
    status: Optional[str] = None,
    search: Optional[str] = None,
    min_score: Optional[int] = None,
    start_filter: Optional[str] = None
):
    apps = StorageManager.get_all_applications()
    
    if status and status != "all":
        norm_req = normalize_status(status)
        apps = [a for a in apps if normalize_status(a.status) == norm_req]
        
    if start_filter == "janvier_2027":
        apps = [a for a in apps if "janvier 2027" in (str(_get_target_dict(a).get("start_date", "")).lower())]
        
    if min_score is not None:
        apps = [a for a in apps if _get_matching_dict(a).get("match_score", 0) >= min_score]
        
    if search:
        s = search.lower()
        def matches_search(a):
            t = _get_target_dict(a)
            return (
                s in t.get("company_name", "").lower()
                or s in t.get("contact_email", "").lower()
                or s in (t.get("job_title") or "").lower()
                or s in (a.subject_line or "").lower()
            )
        apps = [a for a in apps if matches_search(a)]
        
    return [a.model_dump() for a in apps]

@app.get("/api/applications/{app_id}")
async def get_application_detail(app_id: str):
    apps = StorageManager.get_all_applications()
    for app_item in apps:
        if app_item.id == app_id:
            return app_item.model_dump()
    raise HTTPException(status_code=404, detail="Candidature introuvable")

@app.put("/api/applications/{app_id}")
async def update_application(app_id: str, req: UpdateApplicationRequest):
    updates = req.model_dump(exclude_unset=True)
    updated = StorageManager.update_application(app_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Candidature introuvable")
    return updated.model_dump()

@app.post("/api/applications/{app_id}/status")
async def update_application_status_fast(app_id: str, payload: Dict[str, Any] = Body(...)):
    new_status = payload.get("status", "a_examiner")
    updates = {"status": new_status}
    if "applied_at" in payload:
        updates["applied_at"] = payload["applied_at"]
    updated = StorageManager.update_application(app_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Candidature introuvable")
    
    comp_name = updated.target.get("company_name", "Entreprise") if isinstance(updated.target, dict) else getattr(updated.target, "company_name", "Entreprise")
    StorageManager.add_audit_log(
        agent_name="SuiviCandidatures",
        action=AuditActionType.APPROVAL,
        description=f"Statut changé en '{new_status}' pour {comp_name}."
    )
    return {"success": True, "application": updated.model_dump()}

@app.post("/api/applications/deduplicate")
async def deduplicate_applications_endpoint():
    merged_count = StorageManager.deduplicate_all_applications()
    StorageManager.add_audit_log(
        agent_name="AntiDoublonAgent",
        action=AuditActionType.SEARCH,
        description=f"Déduplication multi-sources exécutée : {merged_count} annonce(s) en double fusionnée(s)."
    )
    return {"success": True, "merged_count": merged_count}

@app.delete("/api/applications/{app_id}")
async def delete_application(app_id: str):
    deleted = StorageManager.delete_application(app_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Candidature introuvable")
    return {"success": True, "message": "Candidature supprimée"}

@app.delete("/api/applications")
async def clear_all_applications():
    count = StorageManager.clear_all_applications()
    StorageManager.add_audit_log(
        agent_name="StorageManager",
        action=AuditActionType.SEARCH,
        description=f"Base de candidatures réinitialisée : {count} ancienne(s) offre(s) supprimée(s)."
    )
    return {"success": True, "deleted_count": count}

@app.post("/api/applications/purge-obsolete")
async def purge_obsolete_applications():
    purged = StorageManager.purge_obsolete_applications()
    StorageManager.add_audit_log(
        agent_name="AntiObsolescenceAgent",
        action=AuditActionType.SEARCH,
        description=f"Filtre anti-obsolescence exécuté : {purged} offre(s) expirée(s) purgée(s)."
    )
    return {"success": True, "purged_count": purged}

@app.post("/api/applications/{app_id}/approve")
def approve_and_dispatch(app_id: str):
    apps = StorageManager.get_all_applications()
    app_target = None
    for a in apps:
        if a.id == app_id:
            app_target = a
            break
            
    if not app_target:
        raise HTTPException(status_code=404, detail="Candidature introuvable")

    proof = verification_agent.verify_application(app_target)
    
    updated = StorageManager.update_application(app_id, {
        "status": ApplicationStatus.VERIFIED,
        "verification": proof.model_dump()
    })
    
    comp_name = app_target.target.company_name if hasattr(app_target.target, "company_name") else app_target.target.get("company_name", "Entreprise")
    StorageManager.add_audit_log(
        agent_name="UserInterface & Dispatcher",
        action=AuditActionType.DISPATCH,
        description=f"Candidature approuvée par l'utilisateur, soumise et vérifiée par l'Agent IA pour {comp_name}.",
        target_company=comp_name
    )
    return {"success": True, "application": updated.model_dump(), "proof": proof.model_dump()}

@app.post("/api/applications/{app_id}/send-email")
def send_email_direct(app_id: str):
    apps = StorageManager.get_all_applications()
    app_target = None
    for a in apps:
        if a.id == app_id:
            app_target = a
            break
            
    if not app_target:
        raise HTTPException(status_code=404, detail="Candidature introuvable")

    to_email = app_target.target.contact_email
    subject = app_target.subject_line or f"Candidature Stage PFE Data & IA - Yousra Khallou"
    body = app_target.email_body or ""
    
    # Vérifier si un CV PDF uploadé existe
    uploads_dir = current_dir / "uploads"
    cv_path = uploads_dir / "cv_yousra_khallou.pdf"
    attached = str(cv_path) if cv_path.exists() else None
    
    result = send_real_email_smtp(to_email=to_email, subject=subject, body_text=body, attachment_path=attached)
    
    if result.get("success"):
        proof = verification_agent.verify_application(app_target)
        StorageManager.update_application(app_id, {
            "status": ApplicationStatus.SENT,
            "verification": proof.model_dump()
        })
        comp_name = app_target.target.company_name if hasattr(app_target.target, "company_name") else app_target.target.get("company_name", "Entreprise")
        StorageManager.add_audit_log(
            agent_name="GmailSMTPAgent",
            action=AuditActionType.DISPATCH,
            description=f"Candidature réelle envoyée directement avec CV attaché à {to_email} ({comp_name}).",
            target_company=comp_name
        )
    return result

@app.post("/api/save-credentials")
def save_credentials(data: Dict[str, str] = Body(...)):
    gmail_user = data.get("gmail_user", "").strip()
    gmail_pass = data.get("gmail_password", "").strip()
    
    # Mettre à jour les variables d'environnement en mémoire
    if gmail_user:
        os.environ["GMAIL_USER"] = gmail_user
    if gmail_pass:
        os.environ["GMAIL_APP_PASSWORD"] = gmail_pass
        
    # Mettre à jour le fichier .env
    env_file = current_dir / ".env"
    lines = []
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    filtered = [l for l in lines if not l.startswith("GMAIL_USER=") and not l.startswith("GMAIL_APP_PASSWORD=")]
    if gmail_user:
        filtered.append(f"GMAIL_USER={gmail_user}\n")
    if gmail_pass:
        filtered.append(f"GMAIL_APP_PASSWORD={gmail_pass}\n")
        
    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(filtered)
        
    StorageManager.add_audit_log(
        agent_name="SecurityAgent",
        action=AuditActionType.APPROVAL,
        description="Identifiants Gmail (IMAP/SMTP) mis à jour de manière sécurisée."
    )
    return {"success": True, "message": "Identifiants enregistrés avec succès !"}

@app.get("/api/get-credentials")
def get_credentials():
    gmail_user = os.getenv("GMAIL_USER", "")
    has_pass = bool(os.getenv("GMAIL_APP_PASSWORD", ""))
    return {
        "gmail_user": gmail_user,
        "is_configured": bool(gmail_user and has_pass)
    }

@app.post("/api/test-gmail-connection")
def test_gmail():
    gmail_user = os.getenv("GMAIL_USER", "")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "")
    if not gmail_user or not gmail_pass:
        return {"success": False, "message": "Identifiants non configurés dans .env."}
    try:
        import smtplib
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=5) as server:
            server.login(gmail_user, gmail_pass)
        return {"success": True, "message": f"Connexion Gmail SMTP établie avec succès pour {gmail_user} !"}
    except Exception as e:
        return {"success": False, "message": f"Échec de connexion : {str(e)}"}

@app.post("/api/applications/{app_id}/submit-browser")
def submit_via_browser(app_id: str):
    apps = StorageManager.get_all_applications()
    app_target = None
    for a in apps:
        if a.id == app_id:
            app_target = a
            break
            
    if not app_target or not app_target.autofill_payload:
        raise HTTPException(status_code=404, detail="Candidature ou payload auto-fill introuvable")

    proof = browser_agent.execute_browser_submission(app_target.target, app_target.autofill_payload)
    verification_agent.verify_application(app_target)

    updated = StorageManager.update_application(app_id, {
        "status": ApplicationStatus.VERIFIED,
        "verification": proof.model_dump()
    })
    return {"success": True, "application": updated.model_dump(), "proof": proof.model_dump()}

@app.delete("/api/applications/{app_id}")
def delete_application(app_id: str):
    success = StorageManager.delete_application(app_id)
    if not success:
        raise HTTPException(status_code=404, detail="Candidature introuvable")
    return {"success": True, "message": "Candidature supprimée"}

@app.post("/api/analyze")
def analyze_input(req: AnalyzeRequest):
    if not req.raw_text or not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="Texte brut vide")
        
    profile = StorageManager.get_profile()
    
    try:
        langgraph_app = build_pfe_agent_graph()
        initial_state = {
            "raw_input_text": req.raw_text,
            "profile": profile,
            "min_score_threshold": req.min_score_threshold or 50,
            "extracted_targets": [],
            "company_researches": {},
            "match_results": [],
            "applications": [],
            "error": ""
        }
        final_state = langgraph_app.invoke(initial_state)
        
        generated_apps = final_state.get("applications", [])
        added_apps = StorageManager.add_applications(generated_apps)
        
        return {
            "success": True,
            "targets_count": len(final_state.get("extracted_targets", [])),
            "generated_count": len(generated_apps),
            "new_added_count": len(added_apps),
            "added_applications": [a.model_dump() for a in added_apps],
            "stats": StorageManager.get_stats()
        }
    except Exception as e:
        print(f"[Analyze API Error] {e}")
        raise HTTPException(status_code=500, detail=f"Erreur durant l'analyse : {str(e)}")

@app.post("/api/analyze-sample")
def analyze_sample():
    req = AnalyzeRequest(raw_text=SAMPLE_LINKEDIN_POST, min_score_threshold=50)
    return analyze_input(req)

@app.get("/api/profile")
async def get_profile():
    return StorageManager.get_profile().model_dump()

@app.post("/api/profile")
async def update_profile(profile_data: Dict[str, Any]):
    try:
        profile = CandidateProfile(**profile_data)
        StorageManager.save_profile(profile)
        return {"success": True, "profile": profile.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Données de profil invalides : {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)


# ─────────────────────────────────────────────────────────────────────────────
# MODULE PERSONNALISATION — Tailor Agent Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/applications/{app_id}/personalize")
async def personalize_app(app_id: str):
    """Lance le module de personnalisation sur-mesure pour une candidature.
    Génère le CV adapté (PDF + MD) et la lettre de motivation (PDF + MD)
    dans un dossier dédié applications/<slug>/
    """
    apps = StorageManager.get_all_applications()
    app_obj = next((a for a in apps if a.id == app_id), None)
    if not app_obj:
        raise HTTPException(status_code=404, detail="Candidature introuvable")

    profile = StorageManager.get_profile()

    try:
        from models import ApplicationPersonalizationConfig
        config_path = current_dir / "search_config.json"
        config = ApplicationPersonalizationConfig()
        if config_path.exists():
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            pers_raw = raw.get("application_personalization", {})
            if pers_raw:
                config = ApplicationPersonalizationConfig(**pers_raw)

        updated = personalize_application(
            app=app_obj,
            profile=profile,
            config=config,
            master_cv_path=config.master_cv_path,
            output_dir=config.output_directory
        )
        StorageManager.update_application(app_id, updated)
        return {
            "success": True,
            "app_id": app_id,
            "folder_path": updated.folder_path,
            "cv_pdf": updated.tailored_cv_pdf,
            "cv_md": updated.tailored_cv_tex,
            "letter_pdf": updated.tailored_letter_pdf,
            "letter_md": updated.tailored_letter_md,
            "offer_analysis": updated.offer_analysis,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur personnalisation : {str(e)}")


@app.get("/api/applications/{app_id}/download/cv")
async def download_cv(app_id: str):
    """Télécharge le CV personnalisé PDF de la candidature."""
    apps = StorageManager.get_all_applications()
    app_obj = next((a for a in apps if a.id == app_id), None)
    if not app_obj:
        raise HTTPException(status_code=404, detail="Candidature introuvable")

    pdf_path = getattr(app_obj, "tailored_cv_pdf", None)
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(
            status_code=404,
            detail="CV PDF non généré. Lancez d'abord la personnalisation."
        )
    company = ""
    t = getattr(app_obj, "target", None)
    if isinstance(t, dict):
        company = t.get("company_name", "")
    elif t:
        company = getattr(t, "company_name", "")
    filename = f"CV_Yousra_Khallou_{company}.pdf".replace(" ", "_")
    return FileResponse(pdf_path, media_type="application/pdf",
                        filename=filename, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/applications/{app_id}/download/letter")
async def download_letter(app_id: str):
    """Télécharge la lettre de motivation PDF de la candidature."""
    apps = StorageManager.get_all_applications()
    app_obj = next((a for a in apps if a.id == app_id), None)
    if not app_obj:
        raise HTTPException(status_code=404, detail="Candidature introuvable")

    pdf_path = getattr(app_obj, "tailored_letter_pdf", None)
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(
            status_code=404,
            detail="Lettre PDF non générée. Lancez d'abord la personnalisation."
        )
    company = ""
    t = getattr(app_obj, "target", None)
    if isinstance(t, dict):
        company = t.get("company_name", "")
    elif t:
        company = getattr(t, "company_name", "")
    filename = f"Lettre_Motivation_Yousra_Khallou_{company}.pdf".replace(" ", "_")
    return FileResponse(pdf_path, media_type="application/pdf",
                        filename=filename, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/applications/{app_id}/personalization-status")
async def personalization_status(app_id: str):
    """Vérifie si la personnalisation a déjà été générée pour cette candidature."""
    apps = StorageManager.get_all_applications()
    app_obj = next((a for a in apps if a.id == app_id), None)
    if not app_obj:
        raise HTTPException(status_code=404, detail="Candidature introuvable")

    cv_pdf = getattr(app_obj, "tailored_cv_pdf", None)
    letter_pdf = getattr(app_obj, "tailored_letter_pdf", None)
    folder = getattr(app_obj, "folder_path", None)

    return {
        "personalized": bool(cv_pdf and Path(cv_pdf).exists()),
        "cv_pdf_ready": bool(cv_pdf and Path(cv_pdf).exists()),
        "letter_pdf_ready": bool(letter_pdf and Path(letter_pdf).exists()),
        "folder_path": folder,
        "offer_analysis": getattr(app_obj, "offer_analysis", None),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)

