"""
agents/tailor_agent.py
-----------------------
Agent de personnalisation des candidatures.

Workflow :
  1. Lit le CV maître (Applications/main.md)
  2. Analyse l'offre retenue (MatchingAnalysis + RecruiterTarget)
  3. Demande au LLM d'adapter UNIQUEMENT le profil, les compétences
     prioritaires et l'ordre des projets — sans inventer de compétence.
  4. Génère une lettre de motivation Markdown sur-mesure.
  5. Convertit les deux en PDF via reportlab.
  6. Sauvegarde dans un dossier dédié : applications/<slug>_<id>/
  7. Retourne les chemins dans GeneratedApplication.
"""
import re
import json
import logging
import unicodedata
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    from pfe_agent.config import get_llm, invoke_llm
    from pfe_agent.models import (
        MatchingAnalysis, CandidateProfile,
        GeneratedApplication, ApplicationPersonalizationConfig,
    )
except ImportError:
    from config import get_llm, invoke_llm
    from models import (
        MatchingAnalysis, CandidateProfile,
        GeneratedApplication, ApplicationPersonalizationConfig,
    )

logger = logging.getLogger("TailorAgent")

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _slugify(text: str, max_len: int = 40) -> str:
    """Crée un slug URL-safe depuis un texte."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_-]+", "_", text).strip("_")
    return text[:max_len]


def _read_master_cv(path: str = "Applications/main.md") -> str:
    """Lit le CV maître Markdown et retourne son contenu."""
    cv_path = Path(path)
    if not cv_path.exists():
        # Fallback : cherche dans le dossier du projet
        alt = Path(__file__).parent.parent / path
        if alt.exists():
            cv_path = alt
        else:
            raise FileNotFoundError(f"CV maître introuvable : {path}")
    return cv_path.read_text(encoding="utf-8")


def _get_target_field(target, field: str, default=""):
    """Accède à un champ target (dict ou objet Pydantic)."""
    if isinstance(target, dict):
        return target.get(field, default)
    return getattr(target, field, default)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — ANALYSE DE L'OFFRE
# ─────────────────────────────────────────────────────────────────────────────

OFFER_ANALYSIS_PROMPT = """Tu es un expert en recrutement Tech.
Analyse cette offre de stage PFE et extrais une synthèse structurée STRICTEMENT en JSON.

Format de sortie :
{
  "required_skills": ["skill1", "skill2"],
  "preferred_skills": ["skill3"],
  "key_missions": ["Mission A", "Mission B"],
  "company_tone": "startup agile | grand groupe | PME tech | cabinet conseil",
  "priority_keywords": ["keyword1", "keyword2"],
  "top_projects_to_highlight": ["Nom projet CV le plus pertinent"],
  "suggested_headline": "Titre CV adapté (ex: Data Engineer & IA | RAG & Streaming)",
  "suggested_profile_summary": "Résumé profil ciblé (2 phrases max, à partir du profil réel du candidat)"
}
Ne génère AUCUN texte avant ou après le JSON."""

def analyse_offer(matching: MatchingAnalysis, profile: CandidateProfile) -> dict:
    """Appelle le LLM pour extraire les éléments clés de l'offre."""
    llm = get_llm(temperature=0.1)
    target = matching.target
    
    offer_context = {
        "company": _get_target_field(target, "company_name"),
        "job_title": _get_target_field(target, "job_title"),
        "technologies": _get_target_field(target, "technologies_mentioned", []),
        "raw_context": (_get_target_field(target, "raw_context", "") or "")[:600],
        "match_strengths": matching.matching_strengths,
        "missing_skills": matching.missing_skills,
        "recommended_angle": matching.recommended_angle,
        "candidate_skills": profile.key_skills[:15],
        "candidate_projects": [p.title for p in profile.top_projects],
    }

    from langchain_core.messages import SystemMessage, HumanMessage
    messages = [
        SystemMessage(content=OFFER_ANALYSIS_PROMPT),
        HumanMessage(content=f"Offre à analyser :\n{json.dumps(offer_context, ensure_ascii=False, indent=2)}")
    ]
    
    try:
        response = invoke_llm(llm, messages)
        content = response.content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            lines = lines[1:] if lines[0].startswith("```") else lines
            lines = lines[:-1] if lines and lines[-1].startswith("```") else lines
            content = "\n".join(lines).strip()
        return json.loads(content, strict=False)
    except Exception as e:
        logger.warning(f"[TailorAgent] Analyse offre fallback : {e}")
        return {
            "required_skills": _get_target_field(target, "technologies_mentioned", []),
            "preferred_skills": [],
            "key_missions": matching.matching_strengths[:3],
            "company_tone": "tech",
            "priority_keywords": matching.matching_strengths[:2],
            "top_projects_to_highlight": [profile.top_projects[0].title] if profile.top_projects else [],
            "suggested_headline": "Data Engineer & IA | LLM & Pipelines",
            "suggested_profile_summary": profile.top_projects[0].description if profile.top_projects else ""
        }


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — ADAPTATION DU CV MAÎTRE
# ─────────────────────────────────────────────────────────────────────────────

CV_TAILOR_PROMPT = """Tu es un expert en rédaction de CV pour ingénieurs Data & IA.

Ta mission :
Adapter le CV Maître Markdown pour l'offre cible, en respectant ces RÈGLES ABSOLUES :
1. NE JAMAIS inventer une compétence, un résultat ou une expérience absente du CV maître.
2. Conserver TOUTES les expériences et formations — tu peux seulement réordonner ou accentuer.
3. Adapter le titre (## Profil) et le résumé de profil pour refléter les besoins de l'offre.
4. Réordonner les compétences : mettre en premier celles demandées par l'offre.
5. Mettre en PREMIER les 2–3 projets les plus pertinents (sans supprimer les autres).
6. Remplacer le titre principal par le suggested_headline fourni.
7. Garder strictement le format Markdown du CV maître.
8. Répondre UNIQUEMENT avec le Markdown adapté, sans commentaire, sans JSON autour."""

def tailor_cv_markdown(master_cv: str, offer_analysis: dict, profile: CandidateProfile) -> str:
    """Adapte le CV maître Markdown selon l'analyse de l'offre."""
    llm = get_llm(temperature=0.15)

    from langchain_core.messages import SystemMessage, HumanMessage
    
    context = f"""## Analyse de l'offre cible
- Compétences requises : {', '.join(offer_analysis.get('required_skills', []))}
- Compétences souhaitées : {', '.join(offer_analysis.get('preferred_skills', []))}
- Missions clés : {', '.join(offer_analysis.get('key_missions', []))}
- Mots-clés prioritaires : {', '.join(offer_analysis.get('priority_keywords', []))}
- Projets à mettre en avant : {', '.join(offer_analysis.get('top_projects_to_highlight', []))}
- Nouveau titre suggéré : {offer_analysis.get('suggested_headline', '')}
- Nouveau résumé de profil suggéré : {offer_analysis.get('suggested_profile_summary', '')}

## CV Maître à adapter :
{master_cv}"""

    messages = [
        SystemMessage(content=CV_TAILOR_PROMPT),
        HumanMessage(content=context)
    ]

    try:
        response = invoke_llm(llm, messages, max_retries=3)
        adapted = response.content.strip()
        if adapted.startswith("```"):
            lines = adapted.splitlines()
            lines = lines[1:] if lines[0].startswith("```") else lines
            lines = lines[:-1] if lines and lines[-1].startswith("```") else lines
            adapted = "\n".join(lines).strip()
        # Sécurité : si le LLM retourne moins de la moitié du CV → fallback
        if len(adapted) < len(master_cv) * 0.4:
            logger.warning("[TailorAgent] CV adapté trop court, utilisation du CV maître tel quel")
            return master_cv
        return adapted
    except Exception as e:
        logger.error(f"[TailorAgent] Erreur adaptation CV : {e}")
        return master_cv  # Fallback propre : CV maître non modifié


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — GÉNÉRATION DE LA LETTRE DE MOTIVATION
# ─────────────────────────────────────────────────────────────────────────────

LETTER_PROMPT = """Tu es un expert en rédaction de lettres de motivation pour ingénieurs Data & IA.

RÈGLES D'OR :
1. Structure : Vous / Moi / Nous (3–4 paragraphes).
2. Accroche percutante et spécifique — PAS de "Je me permets de vous contacter...".
3. Citer précisément l'entreprise, le poste, et un projet concret du candidat avec des métriques.
4. Ton professionnel, direct, confiant (pas obséquieux).
5. Mentionner la durée (6 mois) et la disponibilité (Janvier 2027).
6. Inclure la signature complète à la fin.
7. Répondre UNIQUEMENT en Markdown pur (sans JSON autour)."""

def generate_cover_letter_markdown(
    matching: MatchingAnalysis,
    profile: CandidateProfile,
    offer_analysis: dict,
    company_research: Optional[dict] = None
) -> str:
    """Génère la lettre de motivation Markdown personnalisée."""
    llm = get_llm(temperature=0.25)
    target = matching.target
    
    company = _get_target_field(target, "company_name", "l'entreprise")
    job_title = _get_target_field(target, "job_title", "Stage PFE Data & IA")
    contact_name = _get_target_field(target, "contact_name", "Responsable Recrutement")
    location = _get_target_field(target, "location", "Maroc")

    # Projet le plus pertinent
    best_project = None
    for p in profile.top_projects:
        if p.title == matching.best_matching_project:
            best_project = p
            break
    if not best_project and profile.top_projects:
        best_project = profile.top_projects[0]

    context = f"""Candidat : {profile.full_name}
Titre : {profile.title}
Email : {profile.email} | Tél : {profile.phone or '+212 691373401'}
GitHub : {profile.github_url or ''} | LinkedIn : {profile.linkedin_url or ''} | Portfolio : {profile.portfolio_url or ''}
Disponibilité : {profile.availability_date} | Durée : {profile.desired_duration}

Entreprise cible : {company}
Poste : {job_title}
Contact : {contact_name} ({location})
Technologies demandées : {', '.join(_get_target_field(target, 'technologies_mentioned', []))}
Missions clés : {', '.join(offer_analysis.get('key_missions', []))}
Angle recommandé : {matching.recommended_angle}

Projet phare à citer :
- Titre : {best_project.title if best_project else 'Job Intelligent – Plateforme Data & IA'}
- Description : {best_project.description if best_project else ''}
- Stack : {', '.join(best_project.tech_stack[:5]) if best_project else ''}

Points forts du matching :
{chr(10).join('- ' + s for s in matching.matching_strengths[:4])}"""

    from langchain_core.messages import SystemMessage, HumanMessage
    messages = [
        SystemMessage(content=LETTER_PROMPT),
        HumanMessage(content=f"Rédige la lettre de motivation :\n\n{context}")
    ]

    try:
        response = invoke_llm(llm, messages, max_retries=3)
        return response.content.strip()
    except Exception as e:
        logger.error(f"[TailorAgent] Erreur lettre motivation : {e}")
        return f"""# Lettre de Motivation — {job_title} chez {company}

Bonjour {contact_name},

Votre recherche de stagiaire {job_title} chez {company} résonne directement avec mes travaux récents.

{matching.recommended_angle}

Élève ingénieure Data Engineering & IA à l'ENSAH (3ᵉ année cycle ingénieur), disponible à partir de {profile.availability_date} pour une période de {profile.desired_duration}, je serais ravie de vous présenter ma démarche lors d'un bref échange.

Bien cordialement,

**{profile.full_name}**
{profile.title}
{profile.email} | {profile.phone or ''}
{profile.github_url or ''} | {profile.linkedin_url or ''}"""


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — GÉNÉRATION PDF (reportlab)
# ─────────────────────────────────────────────────────────────────────────────

def _md_to_plain(md_text: str) -> str:
    """Conversion Markdown → texte brut pour reportlab (light)."""
    text = re.sub(r"^#{1,6}\s+", "", md_text, flags=re.MULTILINE)  # titres
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)                   # gras
    text = re.sub(r"\*(.+?)\*", r"\1", text)                       # italique
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1 (\2)", text)         # liens
    text = re.sub(r"^-{3,}$", "", text, flags=re.MULTILINE)        # hr
    text = re.sub(r"^:::.*$", "", text, flags=re.MULTILINE)        # pandoc directives
    text = re.sub(r"\\$", "", text, flags=re.MULTILINE)            # backslash fin de ligne
    text = re.sub(r"\\\|", "|", text)                              # \| → |
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _generate_pdf_reportlab(md_content: str, output_path: Path, title: str = "Document") -> bool:
    """Génère un PDF à partir du Markdown via reportlab."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        )
        from reportlab.lib.enums import TA_LEFT, TA_CENTER

        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm,
            title=title
        )

        styles = getSampleStyleSheet()
        story = []

        # Styles personnalisés
        h1_style = ParagraphStyle("H1", parent=styles["Heading1"],
                                   fontSize=14, spaceAfter=4,
                                   textColor=colors.HexColor("#0f172a"), leading=18)
        h2_style = ParagraphStyle("H2", parent=styles["Heading2"],
                                   fontSize=11, spaceAfter=3,
                                   textColor=colors.HexColor("#1d4ed8"), leading=14)
        h3_style = ParagraphStyle("H3", parent=styles["Heading3"],
                                   fontSize=10, spaceAfter=2,
                                   textColor=colors.HexColor("#334155"), leading=13)
        body_style = ParagraphStyle("Body", parent=styles["Normal"],
                                     fontSize=9, leading=13, spaceAfter=2,
                                     textColor=colors.HexColor("#1e293b"))
        bullet_style = ParagraphStyle("Bullet", parent=body_style,
                                       leftIndent=14, bulletIndent=0,
                                       spaceAfter=1)
        center_style = ParagraphStyle("Center", parent=body_style,
                                       alignment=TA_CENTER, spaceAfter=2)

        def safe_para(text, style):
            """Crée un Paragraph en échappant les caractères XML dangereux."""
            text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            try:
                return Paragraph(text, style)
            except Exception:
                return Paragraph(text[:200], style)

        lines = md_content.splitlines()
        i = 0
        while i < len(lines):
            raw = lines[i]
            stripped = raw.strip()
            i += 1

            if not stripped:
                story.append(Spacer(1, 4))
                continue

            # Headers
            if stripped.startswith("# "):
                story.append(safe_para(stripped[2:], h1_style))
                story.append(HRFlowable(width="100%", thickness=1,
                                         color=colors.HexColor("#2563eb"), spaceAfter=4))
            elif stripped.startswith("## "):
                story.append(safe_para(stripped[3:], h2_style))
            elif stripped.startswith("### "):
                story.append(safe_para(stripped[4:], h3_style))
            # Pandoc centering directive
            elif stripped.startswith(":::"):
                pass
            # Bullet
            elif stripped.startswith("- ") or stripped.startswith("* "):
                bullet_text = stripped[2:]
                # Gras
                bullet_text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", bullet_text)
                bullet_text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", bullet_text)
                bullet_text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", bullet_text)
                story.append(Paragraph(f"• {bullet_text}", bullet_style))
            # HR
            elif re.match(r"^-{3,}$", stripped) or re.match(r"^\*{3,}$", stripped):
                story.append(HRFlowable(width="100%", thickness=0.5,
                                         color=colors.HexColor("#e2e8f0"), spaceAfter=3))
            else:
                # Lignes de tableau pandoc ou texte normal
                if re.match(r"^[|:\- ]+$", stripped):
                    continue
                line = stripped
                # Gras/italique inline
                line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
                line = re.sub(r"\*(.+?)\*", r"<i>\1</i>", line)
                line = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", line)
                line = line.replace("\\", "").strip()
                if line:
                    story.append(safe_para(line, body_style))

        doc.build(story)
        logger.info(f"[TailorAgent] PDF généré : {output_path}")
        return True

    except ImportError:
        logger.error("[TailorAgent] reportlab non installé. Installez : pip install reportlab")
        return False
    except Exception as e:
        logger.error(f"[TailorAgent] Erreur génération PDF : {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — ORCHESTRATEUR PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def personalize_application(
    app: GeneratedApplication,
    profile: CandidateProfile,
    config: Optional[ApplicationPersonalizationConfig] = None,
    master_cv_path: str = "Applications/main.md",
    output_dir: str = "applications"
) -> GeneratedApplication:
    """
    Point d'entrée principal du module de personnalisation.
    
    Enrichit un GeneratedApplication existant avec :
    - offer_analysis   : analyse structurée de l'offre
    - tailored_cv_md   : CV Markdown adapté
    - tailored_cv_pdf  : CV PDF téléchargeable
    - tailored_letter_md  : Lettre Markdown modifiable
    - tailored_letter_pdf : Lettre PDF téléchargeable
    - folder_path      : dossier dédié de la candidature
    """
    if config is None:
        config = ApplicationPersonalizationConfig()

    if not config.enabled:
        logger.info("[TailorAgent] Module de personnalisation désactivé.")
        return app

    matching = app.matching
    target = app.target

    # Résoudre les dict vs Pydantic
    if isinstance(matching, dict):
        matching = MatchingAnalysis(**matching)
    if isinstance(target, dict):
        from models import RecruiterTarget
        target = RecruiterTarget(**target)
        matching.target = target

    company = _get_target_field(target, "company_name", "entreprise")
    job_title = _get_target_field(target, "job_title", "stage_pfe")

    # Slug du dossier
    slug = f"{_slugify(company)}_{_slugify(job_title)}_{app.id[:8]}"
    folder = Path(output_dir) / slug
    folder.mkdir(parents=True, exist_ok=True)

    logger.info(f"[TailorAgent] Démarrage personnalisation → {folder}")

    # ── 1. Analyse de l'offre ──────────────────────────────────────────────
    logger.info("[TailorAgent] Étape 1/4 : Analyse de l'offre...")
    offer_analysis = analyse_offer(matching, profile)
    app.offer_analysis = offer_analysis

    # ── 2. CV adapté ──────────────────────────────────────────────────────
    if config.generate_tailored_cv:
        logger.info("[TailorAgent] Étape 2/4 : Adaptation du CV...")
        try:
            master_cv = _read_master_cv(master_cv_path)
        except FileNotFoundError as e:
            logger.error(f"[TailorAgent] {e}")
            master_cv = profile.raw_cv_text or ""

        adapted_cv_md = tailor_cv_markdown(master_cv, offer_analysis, profile)

        # Sauvegarde Markdown éditable
        cv_md_path = folder / "cv_adapte.md"
        cv_md_path.write_text(adapted_cv_md, encoding="utf-8")

        # Génération PDF
        cv_pdf_path = folder / "cv_adapte.pdf"
        pdf_ok = _generate_pdf_reportlab(adapted_cv_md, cv_pdf_path,
                                          title=f"CV – {profile.full_name} – {company}")
        app.tailored_cv_pdf = str(cv_pdf_path) if pdf_ok else None
        app.tailored_cv_tex = str(cv_md_path)  # On stocke le .md comme "editable"

    # ── 3. Lettre de motivation ───────────────────────────────────────────
    if config.generate_motivation_letter:
        logger.info("[TailorAgent] Étape 3/4 : Génération lettre de motivation...")
        letter_md = generate_cover_letter_markdown(
            matching, profile, offer_analysis,
            company_research=app.company_research.model_dump() if app.company_research else None
        )

        letter_md_path = folder / "lettre_motivation.md"
        letter_md_path.write_text(letter_md, encoding="utf-8")

        letter_pdf_path = folder / "lettre_motivation.pdf"
        pdf_ok = _generate_pdf_reportlab(letter_md, letter_pdf_path,
                                          title=f"Lettre – {profile.full_name} – {company}")
        app.tailored_letter_pdf = str(letter_pdf_path) if pdf_ok else None
        app.tailored_letter_md = str(letter_md_path)

    # ── 4. Résumé de l'analyse ────────────────────────────────────────────
    logger.info("[TailorAgent] Étape 4/4 : Sauvegarde résumé...")
    summary = {
        "generated_at": datetime.now().isoformat(),
        "company": company,
        "job_title": job_title,
        "match_score": matching.match_score,
        "offer_analysis": offer_analysis,
        "files": {
            "cv_md": str(folder / "cv_adapte.md"),
            "cv_pdf": app.tailored_cv_pdf,
            "letter_md": str(folder / "lettre_motivation.md"),
            "letter_pdf": app.tailored_letter_pdf,
        }
    }
    (folder / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    app.folder_path = str(folder)
    logger.info(f"[TailorAgent] ✅ Personnalisation terminée → {folder}")
    return app
