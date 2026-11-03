import json
import re
import urllib.parse
from pathlib import Path
from typing import List, Optional, Dict, Any, Set
from datetime import datetime
from models import (
    GeneratedApplication,
    ApplicationStatus,
    CandidateProfile,
    RecruiterTarget,
    MatchingAnalysis,
    SearchConfig,
    AuditLogEntry,
    AuditActionType,
    EpisodicMemoryItem
)

DATA_DIR = Path(__file__).parent
DB_FILE = DATA_DIR / "candidatures_db.json"
PROFILE_FILE = DATA_DIR / "profile_data.json"
SEARCH_CONFIG_FILE = DATA_DIR / "search_config.json"
AUDIT_LOGS_FILE = DATA_DIR / "audit_logs.json"
EPISODIC_MEMORY_FILE = DATA_DIR / "episodic_memory.json"

def _get_target_dict(app: GeneratedApplication) -> dict:
    if isinstance(app.target, RecruiterTarget):
        return app.target.model_dump()
    elif isinstance(app.target, dict):
        return app.target
    return {}

def _get_matching_dict(app: GeneratedApplication) -> dict:
    if isinstance(app.matching, MatchingAnalysis):
        return app.matching.model_dump()
    elif isinstance(app.matching, dict):
        return app.matching
    return {}

def normalize_status(st: Any) -> str:
    s = str(getattr(st, "value", st) or "").lower()
    if s in ["a_postuler"]:
        return "a_postuler"
    if s in ["candidature_envoyee", "envoye", "verifie"]:
        return "candidature_envoyee"
    if s in ["refus", "refuse"]:
        return "refus"
    return "a_examiner"

def normalize_company_name(name: str) -> str:
    if not name:
        return ""
    clean = name.lower()
    clean = re.sub(r'[éèêë]', 'e', clean)
    clean = re.sub(r'[àâä]', 'a', clean)
    clean = re.sub(r'[îï]', 'i', clean)
    clean = re.sub(r'[ôö]', 'o', clean)
    clean = re.sub(r'[ùûü]', 'u', clean)
    clean = re.sub(r'[ç]', 'c', clean)
    
    # Suppression des suffixes génériques et pays pour extraire la marque racine
    noise = [
        "engineering", "technologies", "technology", "consulting", "services",
        "maroc", "morocco", "france", "group", "groupe", "nearshore", "solutions",
        "digital", "international", "sas", "sa", "sarl", "limited", "ltd"
    ]
    for w in noise:
        clean = re.sub(rf'\b{w}\b', '', clean)
    clean = re.sub(r'[^a-z0-9]', '', clean)
    return clean.strip()

def normalize_job_cluster(title: str) -> str:
    if not title:
        return "data_engineer"
    clean = title.lower()
    if any(k in clean for k in ["data eng", "data ing", "donnees", "pyspark", "etl", "big data", "pipeline"]):
        return "data_engineer"
    if any(k in clean for k in ["ia", "ai", "llm", "generative", "genai", "rag", "agent", "nlp", "transformers"]):
        return "ai_engineer"
    if any(k in clean for k in ["data scien", "machine learning", "ml", "deep learning"]):
        return "data_scientist"
    if any(k in clean for k in ["bi", "business intelligence", "power bi", "analytics"]):
        return "bi_analyst"
    clean = re.sub(r'[^a-z0-9]', '', clean)
    return clean[:12]

def canonicalize_url(url: Optional[str]) -> str:
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url.strip())
        canonical = f"{parsed.netloc}{parsed.path}".rstrip("/")
        return canonical.lower()
    except Exception:
        return url.strip().lower()

def compute_application_fingerprints(app: GeneratedApplication) -> List[str]:
    t = _get_target_dict(app)
    keys = []
    
    # 1. URL canonique (déduplication exacte de lien)
    canon_url = canonicalize_url(t.get("source_url"))
    if canon_url and len(canon_url) > 12:
        keys.append(f"url::{canon_url}")
        
    # 2. Racine Entreprise + Cluster Métier (déduplication cross-sources)
    comp_norm = normalize_company_name(t.get("company_name", ""))
    job_cluster = normalize_job_cluster(t.get("job_title", ""))
    if comp_norm:
        keys.append(f"comp_job::{comp_norm}::{job_cluster}")
        
    # 3. Email spécifique
    email = (t.get("contact_email") or "").lower().strip()
    if email and "@" in email and not email.startswith("recrutement@") and not email.startswith("rh@"):
        keys.append(f"email::{email}")
        
    return keys

class StorageManager:
    @staticmethod
    def _init_db():
        if not DB_FILE.exists():
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
        if not AUDIT_LOGS_FILE.exists():
            with open(AUDIT_LOGS_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
        if not EPISODIC_MEMORY_FILE.exists():
            with open(EPISODIC_MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    @classmethod
    def get_all_applications(cls) -> List[GeneratedApplication]:
        cls._init_db()
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                res = []
                for item in data:
                    # Rétrocompatibilité des statuts vers les 4 officiels
                    if "status" in item:
                        item["status"] = normalize_status(item["status"])
                    res.append(GeneratedApplication(**item))
                return res
        except Exception as e:
            print(f"[Storage Error] Erreur chargement DB : {e}")
            return []

    @classmethod
    def save_all_applications(cls, apps: List[GeneratedApplication]):
        cls._init_db()
        with open(DB_FILE, "w", encoding="utf-8") as f:
            export_data = [a.model_dump() for a in apps]
            json.dump(export_data, f, ensure_ascii=False, indent=2)

    @classmethod
    def add_applications(cls, new_apps: List[GeneratedApplication]) -> List[GeneratedApplication]:
        """
        Ajoute les nouvelles candidatures avec déduplication intelligente cross-sources
        (LinkedIn, Site Carrière, Job Boards, Alertes Emails).
        Fusionne les informations en cas de doublon sans créer de seconde entrée.
        """
        existing = cls.get_all_applications()
        
        # Indexer les fingerprints existantes vers leur position
        fingerprint_map: Dict[str, int] = {}
        for idx, app in enumerate(existing):
            for fp in compute_application_fingerprints(app):
                fingerprint_map[fp] = idx
        
        added = []
        for app in new_apps:
            app_fps = compute_application_fingerprints(app)
            matched_idx = None
            for fp in app_fps:
                if fp in fingerprint_map:
                    matched_idx = fingerprint_map[fp]
                    break
            
            if matched_idx is not None:
                # FUSION INTELLIGENTE DES SOURCES
                ex_app = existing[matched_idx]
                ex_dict = ex_app.model_dump()
                new_t = _get_target_dict(app)
                ex_t = ex_dict.get("target", {})
                
                # Enrichir source_platform : ex "LinkedIn & Site Carrière"
                new_plat = new_t.get("source_platform", "")
                ex_plat = ex_t.get("source_platform", "")
                if new_plat and new_plat not in ex_plat:
                    ex_t["source_platform"] = f"{ex_plat} & {new_plat}".strip(" & ")
                
                # Enrichir source_url si l'existant est manquant
                if not ex_t.get("source_url") and new_t.get("source_url"):
                    ex_t["source_url"] = new_t.get("source_url")
                    
                # Conserver la date de début la plus précise
                if "janvier 2027" in (new_t.get("start_date") or "").lower():
                    ex_t["start_date"] = new_t.get("start_date")
                    
                ex_dict["target"] = ex_t
                existing[matched_idx] = GeneratedApplication(**ex_dict)
            else:
                existing.insert(0, app)
                added.append(app)
                # Enregistrer les nouvelles fingerprints
                new_idx = 0
                for fp in app_fps:
                    fingerprint_map[fp] = new_idx
        
        cls.save_all_applications(existing)
        return added

    @classmethod
    def deduplicate_all_applications(cls) -> int:
        """
        Parcourt toutes les candidatures stockées et fusionne tous les doublons existants.
        Retourne le nombre de doublons éliminés.
        """
        apps = cls.get_all_applications()
        initial_count = len(apps)
        unique_apps: List[GeneratedApplication] = []
        seen_fps: Set[str] = set()
        
        for app in apps:
            fps = compute_application_fingerprints(app)
            if any(fp in seen_fps for fp in fps):
                # Doublon détecté : on fusionne avec l'existant
                for ex in unique_apps:
                    ex_fps = compute_application_fingerprints(ex)
                    if any(fp in ex_fps for fp in fps):
                        # Fusionner les plateformes et URLs
                        ex_dict = ex.model_dump()
                        t_ex = ex_dict.get("target", {})
                        t_new = _get_target_dict(app)
                        if t_new.get("source_url") and not t_ex.get("source_url"):
                            t_ex["source_url"] = t_new.get("source_url")
                        p_new = t_new.get("source_platform", "")
                        p_ex = t_ex.get("source_platform", "")
                        if p_new and p_new not in p_ex:
                            t_ex["source_platform"] = f"{p_ex} & {p_new}".strip(" & ")
                        ex_dict["target"] = t_ex
                        break
            else:
                unique_apps.append(app)
                for fp in fps:
                    seen_fps.add(fp)
                    
        cls.save_all_applications(unique_apps)
        return initial_count - len(unique_apps)

    @classmethod
    def update_application(cls, app_id: str, updates: Dict[str, Any]) -> Optional[GeneratedApplication]:
        apps = cls.get_all_applications()
        updated_app = None
        for i, app in enumerate(apps):
            if app.id == app_id:
                app_dict = app.model_dump()
                for k, v in updates.items():
                    if k == "subject_line":
                        app_dict["subject_line"] = v
                    elif k == "email_body":
                        app_dict["email_body"] = v
                    elif k == "cover_letter_snippet":
                        app_dict["cover_letter_snippet"] = v
                    elif k == "status":
                        clean_st = normalize_status(v)
                        app_dict["status"] = clean_st
                        # Horodatage automatique de la date de candidature si marquée envoyée
                        if clean_st == "candidature_envoyee" and not app_dict.get("applied_at"):
                            app_dict["applied_at"] = datetime.now().isoformat()
                    elif k == "applied_at":
                        app_dict["applied_at"] = v
                    elif k == "notes":
                        app_dict["notes"] = v
                    elif k == "verification":
                        app_dict["verification"] = v
                    elif k in ["contact_email", "company_name", "job_title", "source_url", "start_date"]:
                        if isinstance(app_dict.get("target"), dict):
                            app_dict["target"][k] = v
                
                app_dict["updated_at"] = datetime.now().isoformat()
                updated_app = GeneratedApplication(**app_dict)
                apps[i] = updated_app
                break
        
        if updated_app:
            cls.save_all_applications(apps)
        return updated_app

    @classmethod
    def delete_application(cls, app_id: str) -> bool:
        apps = cls.get_all_applications()
        filtered = [a for a in apps if a.id != app_id]
        if len(filtered) < len(apps):
            cls.save_all_applications(filtered)
            return True
        return False

    @classmethod
    def clear_all_applications(cls) -> int:
        apps = cls.get_all_applications()
        count = len(apps)
        cls.save_all_applications([])
        return count

    @classmethod
    def purge_obsolete_applications(cls) -> int:
        apps = cls.get_all_applications()
        valid = []
        for a in apps:
            t = _get_target_dict(a)
            ctx = (t.get("raw_context") or "").lower()
            posted = (t.get("posted_date") or "").lower()
            if any(bad in ctx or bad in posted for bad in ["avril 2024", "mai 2024", "avril 2025", "mai 2025", "2023", "2024"]):
                continue
            valid.append(a)
        purged = len(apps) - len(valid)
        if purged > 0:
            cls.save_all_applications(valid)
        return purged

    @classmethod
    def get_stats(cls) -> Dict[str, int]:
        apps = cls.get_all_applications()
        
        def get_score(a: GeneratedApplication) -> int:
            m = _get_matching_dict(a)
            return m.get("match_score", 0)

        # Les 4 statuts officiels demandés par l'utilisateur
        a_examiner = sum(1 for a in apps if normalize_status(a.status) == "a_examiner")
        a_postuler = sum(1 for a in apps if normalize_status(a.status) == "a_postuler")
        candidature_envoyee = sum(1 for a in apps if normalize_status(a.status) == "candidature_envoyee")
        refus = sum(1 for a in apps if normalize_status(a.status) == "refus")
        
        # Filtre et priorité Janvier 2027
        janvier_2027_count = sum(1 for a in apps if "janvier 2027" in (str(_get_target_dict(a).get("start_date", "")).lower()))

        return {
            "total": len(apps),
            "a_examiner": a_examiner,
            "a_postuler": a_postuler,
            "candidature_envoyee": candidature_envoyee,
            "refus": refus,
            "janvier_2027": janvier_2027_count,
            "hot_matches": sum(1 for a in apps if get_score(a) >= 80),
            # Rétrocompatibilité UI
            "a_valider": a_examiner,
            "envoye": candidature_envoyee,
            "brouillon": a_postuler,
            "relance": sum(1 for a in apps if a.status == ApplicationStatus.FOLLOW_UP)
        }

    @classmethod
    def get_profile(cls) -> CandidateProfile:
        if not PROFILE_FILE.exists():
            return CandidateProfile(
                full_name="Yousra Khallou",
                title="Élève Ingénieure en Data Engineering & IA (ENSAH)",
                email="khallouyoussra84@gmail.com"
            )
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return CandidateProfile(**data)

    @classmethod
    def save_profile(cls, profile: CandidateProfile):
        with open(PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(profile.model_dump(), f, ensure_ascii=False, indent=2)

    @classmethod
    def get_search_config(cls) -> SearchConfig:
        if not SEARCH_CONFIG_FILE.exists():
            cfg = SearchConfig()
            cls.save_search_config(cfg)
            return cfg
        try:
            with open(SEARCH_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return SearchConfig(**data)
        except Exception as e:
            print(f"[Storage Error] Erreur chargement SearchConfig : {e}")
            return SearchConfig()

    @classmethod
    def save_search_config(cls, cfg: SearchConfig):
        with open(SEARCH_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg.model_dump(), f, ensure_ascii=False, indent=2)

    @classmethod
    def get_audit_logs(cls) -> List[AuditLogEntry]:
        cls._init_db()
        try:
            with open(AUDIT_LOGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [AuditLogEntry(**item) for item in data]
        except Exception as e:
            print(f"[Storage Error] Erreur chargement AuditLogs : {e}")
            return []

    @classmethod
    def add_audit_log(cls, agent_name: str, action: AuditActionType, description: str, target_company: Optional[str] = None, status: str = "succes"):
        cls._init_db()
        entry = AuditLogEntry(
            agent_name=agent_name,
            action=action,
            description=description,
            target_company=target_company,
            status=status
        )
        logs = cls.get_audit_logs()
        logs.insert(0, entry)
        with open(AUDIT_LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump([l.model_dump() for l in logs[:100]], f, ensure_ascii=False, indent=2)

    @classmethod
    def get_episodic_memory(cls) -> List[EpisodicMemoryItem]:
        cls._init_db()
        try:
            with open(EPISODIC_MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [EpisodicMemoryItem(**item) for item in data]
        except Exception as e:
            print(f"[Storage Error] Erreur chargement EpisodicMemory : {e}")
            return []

    @classmethod
    def add_episodic_memory(cls, item: EpisodicMemoryItem):
        cls._init_db()
        memory = cls.get_episodic_memory()
        memory.insert(0, item)
        with open(EPISODIC_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump([m.model_dump() for m in memory[:100]], f, ensure_ascii=False, indent=2)
