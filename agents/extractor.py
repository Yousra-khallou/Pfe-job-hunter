import json
from typing import List
from langchain_core.messages import SystemMessage, HumanMessage

try:
    from pfe_agent.config import get_llm
    from pfe_agent.models import RecruiterTarget
except ImportError:
    from config import get_llm
    from models import RecruiterTarget

EXTRACTOR_SYSTEM_PROMPT = """Tu es un Agent Expert en Extraction de Données de Recrutement.
Ta mission est d'analyser un texte brut (post LinkedIn, liste d'emails, alertes de recrutement, descriptions d'offres) et d'extraire de manière structurée chaque contact ou offre d'emploi / stage.

Pour chaque cible identifiée, extrais :
- company_name : Nom de l'entreprise (ou "Entreprise non spécifiée" si absent)
- contact_email : Adresse email de contact RH / recrutement (Obligatoire, vérifie le format email)
- contact_name : Nom de la personne RH ou du recruteur si mentionné (sinon "Responsable Recrutement")
- job_title : Intitulé du poste ou domaine recherché (ex: "Stage PFE Data & IA", "Data Engineer", etc.)
- location : Ville / Pays si mentionné (ex: Casablanca, Rabat, Paris, Remote, etc.)
- technologies_mentioned : Liste des technos ou compétences citées (ex: Python, Spark, Kafka, Airflow, LLM, Docker...)
- raw_context : La phrase ou le paragraphe source mentionnant cette opportunité

Tu DOIS répondre STRICTEMENT au format JSON avec la structure suivante :
{
  "targets": [
    {
      "company_name": "...",
      "contact_email": "...",
      "contact_name": "...",
      "job_title": "...",
      "location": "...",
      "technologies_mentioned": ["..."],
      "raw_context": "..."
    }
  ]
}
Ne génère AUCUN texte avant ou après le JSON.
"""

def extract_recruiter_targets(raw_text: str) -> List[RecruiterTarget]:
    llm = get_llm(temperature=0.1)
    
    messages = [
        SystemMessage(content=EXTRACTOR_SYSTEM_PROMPT),
        HumanMessage(content=f"Voici le texte brut à analyser :\n\n---\n{raw_text}\n---")
    ]
    
    response = llm.invoke(messages)
    content = response.content.strip()
    
    if content.startswith("```"):
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()
        
    try:
        data = json.loads(content)
        targets_raw = data.get("targets", [])
        return [RecruiterTarget(**t) for t in targets_raw]
    except Exception as e:
        print(f"[Extractor Error] Erreur parsing JSON : {e}")
        return []
