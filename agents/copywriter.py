import json
from langchain_core.messages import SystemMessage, HumanMessage

try:
    from pfe_agent.config import get_llm, invoke_llm
    from pfe_agent.models import MatchingAnalysis, CandidateProfile, GeneratedApplication
except ImportError:
    from config import get_llm, invoke_llm
    from models import MatchingAnalysis, CandidateProfile, GeneratedApplication

COPYWRITER_SYSTEM_PROMPT = """Tu es un Expert Copywriter d'élite pour les candidatures Tech et Stages PFE d'Ingénieurs.
Ta mission est de concevoir un pack de candidature ultra-personnalisé comprenant :
1. Un Email d'approche percutant et direct prêt à l'envoi.
2. Une Lettre de Motivation complète et sur-mesure (s'inspirant du style et modèle du candidat si fourni).
3. Une Adaptation de CV ciblée mettant en valeur les dépôts GitHub et compétences clés demandées par le poste.

RÈGLES D'OR ABSOLUES :
1. COMMENCE DIRECTEMENT avec une accroche percutante et spécifique.
   - BANNIR TOTALEMENT : "Je me permets de vous contacter...", "J'ai l'honneur de...", "Je suis ravi de vous écrire...", "J'ai découvert votre annonce...".
   - EXEMPLE D'ACCROCHE FORTE : "Votre recherche de stagiaire Data Engineer & IA chez {company} résonne directement avec mes récents travaux chez {stage/projet}." ou "Ayant conçu une architecture Data Lake Bronze/Silver/Gold sous PySpark et Airflow, votre opportunité {job_title} a particulièrement retenu mon attention."
2. STRUCTURE DU CORPS DE L'EMAIL :
   - Paragraphe 1 (Accroche & Contexte) : Citation précise du poste et de l'entreprise.
   - Paragraphe 2 (Preuve de valeur concrète) : Démonstration technique avec le projet phare / dépôt GitHub retenu ({featured_project}). Citer des métriques, des technos précises et la valeur créée.
   - Paragraphe 3 (Proposition PFE) : Durée de 6 mois à partir de {availability}, mobilité internationale, motivation pour leurs projets Data & IA.
   - Paragraphe 4 (Call to Action) : Invitation naturelle à un court échange de 15 minutes (téléphonique ou visio).
3. LETTRE DE MOTIVATION (cover_letter_snippet) :
   - Rédige une lettre de motivation complète et percutante (3 à 4 paragraphes structurés : Vous / Moi / Nous), alignée sur les technologies et défis de l'entreprise cible.
4. ADAPTATION CV (tailored_cv_summary) :
   - Rédige une synthèse de profil optimisée et liste les 3 projets GitHub et 5 compétences clés prioritaires à mettre en avant sur le CV pour cette offre.
5. SIGNATURE :
   - Yousra Khallou
   - Élève Ingénieure Data Engineering & IA – ENSAH
   - Téléphone & Email
   - Liens GitHub / Portfolio / LinkedIn

Format de sortie STRICTEMENT en JSON :
{
  "subject_line": "Candidature Stage PFE Data Engineering & IA – Yousra Khallou",
  "email_body": "Corps complet de l'email prêt à l'envoi",
  "cover_letter_snippet": "Lettre de motivation complète sur-mesure",
  "tailored_cv_summary": "Synthèse de profil et projets GitHub recommandés pour le CV ciblé"
}
Ne génère AUCUN texte avant ou après le JSON.
"""

def generate_tailored_application(matching: MatchingAnalysis, profile: CandidateProfile) -> GeneratedApplication:
    llm = get_llm(temperature=0.2)
    
    target_obj = matching.target if hasattr(matching.target, 'company_name') else matching.target if isinstance(matching.target, dict) else {}
    target_company = target_obj.get("company_name") if isinstance(target_obj, dict) else getattr(target_obj, "company_name", "Entreprise")
    contact_name = target_obj.get("contact_name") if isinstance(target_obj, dict) else getattr(target_obj, "contact_name", "Responsable Recrutement")
    job_title = target_obj.get("job_title") if isinstance(target_obj, dict) else getattr(target_obj, "job_title", "Stage PFE Data & IA")
    location = target_obj.get("location") if isinstance(target_obj, dict) else getattr(target_obj, "location", "Maroc")
    technologies = target_obj.get("technologies_mentioned") if isinstance(target_obj, dict) else getattr(target_obj, "technologies_mentioned", [])
    raw_context = target_obj.get("raw_context") if isinstance(target_obj, dict) else getattr(target_obj, "raw_context", "")
    # Truncate raw_context to avoid overflowing model context window
    if raw_context and len(raw_context) > 800:
        raw_context = raw_context[:800] + "..."

    chosen_project = None
    for p in profile.top_projects:
        if p.title == matching.best_matching_project:
            chosen_project = p
            break
    if not chosen_project and profile.top_projects:
        chosen_project = profile.top_projects[0]
        
    context_data = {
        "candidate": {
            "name": profile.full_name,
            "title": profile.title,
            "email": profile.email,
            "phone": profile.phone,
            "location": profile.location,
            "linkedin": profile.linkedin_url,
            "github": profile.github_url,
            "portfolio": profile.portfolio_url,
            "sample_cover_letter_template": getattr(profile, "sample_cover_letter", ""),
            "availability": profile.availability_date,
            "duration": profile.desired_duration,
            "key_skills": profile.key_skills,
            "featured_project": chosen_project.model_dump() if chosen_project else None,
            "all_github_projects": [p.model_dump() for p in profile.top_projects[:4]]
        },
        "target_company": {
            "name": target_company,
            "contact_name": contact_name,
            "job_title": job_title,
            "location": location,
            "technologies": technologies,
            "raw_context": raw_context
        },
        "strategy": {
            "match_score": matching.match_score,
            "strengths": matching.matching_strengths,
            "recommended_angle": matching.recommended_angle
        }
    }
    
    messages = [
        SystemMessage(content=COPYWRITER_SYSTEM_PROMPT),
        HumanMessage(content=f"Rédige le pack de candidature sur-mesure (Email, Lettre de motivation, Adaptation CV) pour cette opportunité :\n\n{json.dumps(context_data, ensure_ascii=False, indent=2)}")
    ]
    
    try:
        response = invoke_llm(llm, messages)
        content = response.content.strip()

        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        data = json.loads(content, strict=False)
        return GeneratedApplication(
            target=matching.target,
            matching=matching,
            subject_line=data.get("subject_line", f"Candidature Stage PFE Data & IA – {profile.full_name}"),
            email_body=data.get("email_body", ""),
            cover_letter_snippet=data.get("cover_letter_snippet", ""),
            tailored_cv_summary=data.get("tailored_cv_summary", "")
        )
    except Exception as e:
        print(f"[Copywriter Error] Erreur LLM ou parsing : {e}")
        fallback_body = f"""Bonjour {contact_name},

Votre opportunité pour le poste {job_title} chez {target_company} résonne directement avec mes récents travaux en {profile.title}.

Dans le cadre de mon projet phare ({chosen_project.title if chosen_project else 'Data & IA'}), j'ai conçu un pipeline de données performant utilisant {', '.join(chosen_project.tech_stack[:4]) if chosen_project else 'Python & Spark'}.

Élève ingénieure en dernière année à l'ENSAH, je suis à la recherche d'un stage PFE de {profile.desired_duration} à compter de {profile.availability_date}. Mon profil apporte une expertise concrète sur {matching.recommended_angle}.

Je serais ravie de pouvoir vous présenter ma démarche lors d'un bref échange téléphonique de 15 minutes.

Bien cordialement,

{profile.full_name}
{profile.title}
Tel: {profile.phone or '+212 600000000'} | Email: {profile.email}
GitHub: {profile.github_url or ''} | LinkedIn: {profile.linkedin_url or ''}"""

        return GeneratedApplication(
            target=matching.target,
            matching=matching,
            subject_line=f"Candidature Stage PFE Data & IA – {profile.full_name} / {target_company}",
            email_body=fallback_body,
            cover_letter_snippet="",
            tailored_cv_summary=""
        )
