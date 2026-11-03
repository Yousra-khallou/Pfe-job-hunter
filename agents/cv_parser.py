import io
import json
from typing import Optional
import pypdf
from langchain_core.messages import SystemMessage, HumanMessage

try:
    from pfe_agent.config import get_llm
    from pfe_agent.models import CandidateProfile, ProjectHighlight
except ImportError:
    from config import get_llm
    from models import CandidateProfile, ProjectHighlight

CV_PARSER_SYSTEM_PROMPT = """Tu es un Agent IA Expert en Parsing et Analyse de CV Techniques d'Ingénieurs.
Ta mission est d'analyser le texte extrait d'un CV au format PDF et de générer un objet profil structuré complet.

Pour le candidat, extrais :
- full_name : Nom et prénom
- title : Titre du profil (ex: Élève Ingénieure en Data Engineering & IA)
- email : Email
- phone : Téléphone
- location : Ville/Pays
- linkedin_url : Lien LinkedIn si disponible
- github_url : Lien GitHub si disponible
- desired_duration : Durée de stage (ex: 6 mois)
- availability_date : Date de disponibilité (ex: Janvier 2027)
- pfe_topics_sought : Liste des thématiques recherchées (ex: LLM, RAG, PySpark, Data Lake)
- key_skills : Liste des compétences techniques (ex: Python, SQL, Spark, Airflow, FastAPI, Docker, Qdrant)
- top_projects : Liste des projets phares avec :
  - title : Nom du projet
  - description : Résumé court et impact
  - tech_stack : Liste des technologies utilisées

Réponds STRICTEMENT au format JSON correspondant à cette structure. Ne génère AUCUN texte avant ou après le JSON.
"""

def parse_pdf_cv_bytes(pdf_bytes: bytes) -> CandidateProfile:
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    extracted_text = ""
    for page in reader.pages:
        txt = page.extract_text()
        if txt:
            extracted_text += txt + "\n"
            
    if not extracted_text.strip():
        raise ValueError("Impossible d'extraire du texte du fichier PDF du CV.")
        
    llm = get_llm(temperature=0.1)
    
    messages = [
        SystemMessage(content=CV_PARSER_SYSTEM_PROMPT),
        HumanMessage(content=f"Voici le texte brut extrait du CV PDF :\n\n---\n{extracted_text}\n---")
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
        
    data = json.loads(content, strict=False)
    
    projects_raw = data.get("top_projects", [])
    top_projects = [ProjectHighlight(**p) for p in projects_raw]
    
    return CandidateProfile(
        full_name=data.get("full_name", "Yousra Khallou"),
        title=data.get("title", "Élève Ingénieure en Data Engineering & IA (ENSAH)"),
        email=data.get("email", "khallouyoussra84@gmail.com"),
        phone=data.get("phone", "+212 691373401"),
        location=data.get("location", "Maroc (Mobilité internationale)"),
        linkedin_url=data.get("linkedin_url", "https://linkedin.com/in/yousra-khallou"),
        github_url=data.get("github_url", "https://github.com/yousra-khallou"),
        desired_duration=data.get("desired_duration", "6 mois"),
        availability_date=data.get("availability_date", "Janvier 2027"),
        pfe_topics_sought=data.get("pfe_topics_sought", [
            "Generative AI & LLMs avancés (RAG, Qdrant)",
            "Data Engineering & Big Data (Spark, Airflow, Kafka)"
        ]),
        key_skills=data.get("key_skills", ["Python", "SQL", "Spark", "Airflow", "FastAPI", "Docker", "Qdrant"]),
        top_projects=top_projects
    )
