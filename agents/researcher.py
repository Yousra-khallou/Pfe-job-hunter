import json
from langchain_core.messages import SystemMessage, HumanMessage

try:
    from pfe_agent.config import get_llm, invoke_llm
    from pfe_agent.models import RecruiterTarget, CompanyResearch
except ImportError:
    from config import get_llm, invoke_llm
    from models import RecruiterTarget, CompanyResearch

RESEARCHER_SYSTEM_PROMPT = """Tu es un Agent IA Spécialiste en Intelligence Économique et Recherche d'Entreprises.
Ta mission est d'analyser les informations disponibles sur une entreprise cible et son annonce de recrutement pour générer une synthèse structurée de son activité, sa culture technique et ses valeurs.

Données d'entrée :
- Nom de l'entreprise
- Poste recherché
- Contexte brut de l'annonce / technologies citées

Tu DOIS répondre STRICTEMENT en JSON sous la forme suivante :
{
  "company_name": "...",
  "industry": "...",
  "tech_culture_summary": "Description concise de l'environnement et de la culture technique",
  "key_products_or_clients": ["Projet 1 / Client A", "Technologie phare 2"],
  "values_and_vision": "Résumé de l'orientation stratégique et des valeurs clés"
}
Ne génère AUCUN texte avant ou après le JSON.
"""

def research_company_target(target: RecruiterTarget) -> CompanyResearch:
    llm = get_llm(temperature=0.2)
    
    target_dict = target.model_dump() if hasattr(target, "model_dump") else target
    company_name = target_dict.get("company_name", "Entreprise Non Spécifiée")
    job_title = target_dict.get("job_title", "Stage PFE")
    raw_context = target_dict.get("raw_context", "")
    technologies = target_dict.get("technologies_mentioned", [])
    
    prompt = f"""Cible Entreprise : {company_name}
Intitulé Poste : {job_title}
Technologies citées : {', '.join(technologies)}
Contexte : {raw_context}
"""

    messages = [
        SystemMessage(content=RESEARCHER_SYSTEM_PROMPT),
        HumanMessage(content=prompt)
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
        return CompanyResearch(
            company_name=company_name,
            industry=data.get("industry", "Technologies & Data"),
            tech_culture_summary=data.get("tech_culture_summary", f"Entreprise innovante dans le domaine {job_title}"),
            key_products_or_clients=data.get("key_products_or_clients", technologies),
            values_and_vision=data.get("values_and_vision", "Excellence technique et innovation")
        )
    except Exception as e:
        print(f"[Researcher Error] Erreur parsing : {e}")
        return CompanyResearch(
            company_name=company_name,
            industry="Ingénierie & Technologies",
            tech_culture_summary=f"Entreprise spécialisée dans les solutions IT, Data & IA ({job_title})",
            key_products_or_clients=technologies if technologies else ["Pipelines Data", "IA Avancée"],
            values_and_vision="Transformation digitale et innovation logicielle"
        )
