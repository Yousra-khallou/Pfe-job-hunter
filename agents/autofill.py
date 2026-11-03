import json
from langchain_core.messages import SystemMessage, HumanMessage

try:
    from pfe_agent.config import get_llm
    from pfe_agent.models import CandidateProfile, RecruiterTarget, MatchingAnalysis, CompanyResearch, FormAutofillPayload
except ImportError:
    from config import get_llm
    from models import CandidateProfile, RecruiterTarget, MatchingAnalysis, CompanyResearch, FormAutofillPayload

AUTOFILL_SYSTEM_PROMPT = """Tu es un Agent IA Expert en Automatisation de Candidatures et Formulaires Web de Recrutement.
Ta mission est de construire un payload JSON complet de pré-remplissage pour les portails de recrutement (LinkedIn, Welcome to the Jungle, Lever, Greenhouse, etc.).

Tu dois générer des réponses concises, percutantes et ciblées pour les questions fréquentes des formulaires :
- why_us_answer : Réponse précise à "Pourquoi souhaitez-vous rejoindre notre entreprise ?" (2-3 phrases).
- top_skill_highlight : Réponse à "Quelle est votre plus grande force technique ?" (1-2 phrases avec exemple de projet).
- custom_form_answers : Réponses à des questions types (disponibilité, mobilité, prétentions, lien portfolio/GitHub).

Réponds STRICTEMENT au format JSON avec cette structure :
{
  "why_us_answer": "...",
  "top_skill_highlight": "...",
  "custom_form_answers": {
    "disponibilite": "Disponibilité immédiate à partir de Janvier 2027 pour une durée de 6 mois",
    "mobilite": "Maroc avec mobilité internationale",
    "contrat_souhaite": "Stage de Fin d'Études (PFE) / Pré-embauche",
    "portfolio_github": "https://github.com/yousra-khallou"
  }
}
Ne génère AUCUN texte avant ou après le JSON.
"""

def generate_form_autofill_payload(
    profile: CandidateProfile,
    target: RecruiterTarget,
    matching: MatchingAnalysis,
    research: CompanyResearch
) -> FormAutofillPayload:
    llm = get_llm(temperature=0.2)
    
    target_dict = target.model_dump() if hasattr(target, "model_dump") else target
    company_name = target_dict.get("company_name", "Entreprise Cible")
    job_title = target_dict.get("job_title", "Stage PFE")
    
    context = {
        "candidate": {
            "name": profile.full_name,
            "title": profile.title,
            "email": profile.email,
            "phone": profile.phone,
            "location": profile.location,
            "github": profile.github_url,
            "linkedin": profile.linkedin_url,
            "availability": profile.availability_date,
            "duration": profile.desired_duration,
            "top_project": matching.best_matching_project
        },
        "target": {
            "company": company_name,
            "job": job_title,
            "recommended_angle": matching.recommended_angle
        },
        "company_research": research.model_dump() if hasattr(research, "model_dump") else research
    }
    
    messages = [
        SystemMessage(content=AUTOFILL_SYSTEM_PROMPT),
        HumanMessage(content=f"Génère le payload de pré-remplissage de formulaire web :\n\n{json.dumps(context, ensure_ascii=False, indent=2)}")
    ]
    
    try:
        response = llm.invoke(messages)
        content = response.content.strip()
        
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()
            
        data = json.loads(content, strict=False)
        
        return FormAutofillPayload(
            full_name=profile.full_name,
            email=profile.email,
            phone=profile.phone or "+212 691373401",
            location=profile.location or "Maroc",
            linkedin_url=profile.linkedin_url or "",
            github_url=profile.github_url or "",
            availability=profile.availability_date,
            expected_duration=profile.desired_duration,
            why_us_answer=data.get("why_us_answer", f"Votre opportunité {job_title} chez {company_name} s'aligne directement avec mon expertise en Data Engineering & IA."),
            top_skill_highlight=data.get("top_skill_highlight", f"Maîtrise de la conception de pipelines Big Data et architectures RAG/LLM avec PySpark, Airflow et FastAPI."),
            custom_form_answers=data.get("custom_form_answers", {
                "disponibilite": profile.availability_date,
                "duree": profile.desired_duration,
                "contrat": "Stage PFE (6 mois)"
            })
        )
    except Exception as e:
        print(f"[Autofill Error] Erreur parsing : {e}")
        return FormAutofillPayload(
            full_name=profile.full_name,
            email=profile.email,
            phone=profile.phone or "+212 691373401",
            location=profile.location or "Maroc",
            linkedin_url=profile.linkedin_url or "",
            github_url=profile.github_url or "",
            availability=profile.availability_date,
            expected_duration=profile.desired_duration,
            why_us_answer=f"Votre poste {job_title} chez {company_name} correspond parfaitement à ma spécialisation en Data & IA.",
            top_skill_highlight="Expertise pratique en pipelines ETL, architectures RAG/LLM et développement API FastAPI.",
            custom_form_answers={
                "disponibilite": profile.availability_date,
                "contrat": "Stage PFE"
            }
        )
