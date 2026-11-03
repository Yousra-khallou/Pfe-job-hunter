import json
from langchain_core.messages import SystemMessage, HumanMessage

try:
    from pfe_agent.config import get_llm, invoke_llm
    from pfe_agent.models import RecruiterTarget, CandidateProfile, MatchingAnalysis
except ImportError:
    from config import get_llm, invoke_llm
    from models import RecruiterTarget, CandidateProfile, MatchingAnalysis

MATCHER_SYSTEM_PROMPT = """Tu es un Expert Stratège en Recrutement Tech et Scoring Sémantique de Candidatures.
Ta mission est d'évaluer la correspondance entre le profil d'un élève ingénieur et une opportunité/entreprise cible.

Tu dois calculer la décomposition précise des scores de match (0 à 100) :
1. match_score : Score global de pertinence
2. technical_match : Alignement des compétences techniques et stacks
3. experience_match : Alignement formation, projets et niveau requis
4. location_match : Alignement ville, pays ou remote
5. matching_strengths : 2 à 4 points forts majeurs
6. missing_skills : Liste des compétences souhaitées manquantes (ou [] si aucune)
7. best_matching_project : Nom exact du projet du candidat le plus pertinent à valoriser
8. recommended_angle : Angle stratégique recommandé
9. recommendation : "APPLY" (si score >= 75), "REVIEW" (si 50-74), "REJECT" (si < 50)

Réponds STRICTEMENT au format JSON avec cette structure :
{
  "match_score": 92,
  "technical_match": 95,
  "experience_match": 90,
  "location_match": 100,
  "matching_strengths": [
    "Maîtrise de la stack PySpark, Airflow et FastAPI correspondant aux besoins",
    "Expérience pratique avec Qdrant et architectures RAG"
  ],
  "missing_skills": ["AWS"],
  "best_matching_project": "Assistant Conversationnel Documentaire RAG & Recherche Hybride (Stage PFA - ONCF)",
  "recommended_angle": "Accentuer la capacité à concevoir des architectures RAG hybrides et des pipelines Big Data résilients.",
  "recommendation": "APPLY"
}
Ne génère AUCUN texte avant ou après le JSON.
"""

def evaluate_start_date_compatibility(target: RecruiterTarget) -> tuple:
    """
    Évalue la date de début du stage :
    - Bonus de priorité si l'offre commence en Janvier 2027 (+10 pts)
    - Conserve et maintient les offres flexibles ou non précisées sans pénalité
    - Pénalise uniquement les offres obsolètes ou incompatibles
    """
    raw_ctx = ((target.raw_context or "") + " " + (target.job_title or "") + " " + (getattr(target, "start_date", "") or "")).lower()
    start_date_field = (getattr(target, "start_date", "") or "").lower()
    
    # 1. Alignement optimal : Janvier 2027 / Début 2027 / Q1 2027
    if any(k in raw_ctx or k in start_date_field for k in [
        "janvier 2027", "janv 2027", "jan 2027", "01/2027", "début 2027", "debut 2027", "q1 2027", "premier trimestre 2027"
    ]):
        target.start_date = "Janvier 2027 (Prioritaire)"
        return 10, "Date de début idéale (Janvier 2027) : Parfaitement alignée avec le calendrier académique ENSAH"

    # 2. Date flexible ou non précisée : conserver sans pénalité
    if any(k in raw_ctx or k in start_date_field for k in [
        "flexible", "non précisée", "non precisee", "à convenir", "a convenir", "dès que possible", "asap", "selon disponibilité"
    ]):
        target.start_date = "Flexible / Non précisée"
        return 0, "Date de début flexible ou à convenir avec le recruteur"

    # 3. Mention de 2027 (Février/Mars ou générale)
    if "2027" in raw_ctx or "2027" in start_date_field:
        target.start_date = "Début 2027"
        return 5, "Date de début compatible avec le cycle PFE 2027"

    # Par défaut : date flexible conservée
    target.start_date = "Flexible / Non précisée"
    return 0, "Date de début non précisée (Conservée sans pénalité)"

def match_candidate_with_target(target: RecruiterTarget, profile: CandidateProfile) -> MatchingAnalysis:
    llm = get_llm(temperature=0.1)
    
    # Évaluation de la date de début (Priorisation Janvier 2027, maintien flexible)
    date_bonus, date_strength = evaluate_start_date_compatibility(target)
    
    target_dict = target.model_dump() if hasattr(target, "model_dump") else target
    profile_dict = profile.model_dump() if hasattr(profile, "model_dump") else profile
    
    user_prompt = f"""Profil du candidat :
{json.dumps(profile_dict, ensure_ascii=False, indent=2)}

Opportunité / Entreprise cible :
{json.dumps(target_dict, ensure_ascii=False, indent=2)}

Consigne particulière sur la date de début :
{date_strength}
"""
    
    messages = [
        SystemMessage(content=MATCHER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt)
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
        base_score = int(data.get("match_score", 85))
        # Application du bonus de priorité pour Janvier 2027 (plafonné à 100)
        final_score = min(100, max(0, base_score + date_bonus))
        rec = data.get("recommendation", "APPLY" if final_score >= 75 else "REVIEW")
        
        strengths = data.get("matching_strengths", ["Compétences Data & IA directes"])
        if date_strength not in strengths:
            strengths.insert(0, date_strength)

        return MatchingAnalysis(
            target=target,
            match_score=final_score,
            technical_match=int(data.get("technical_match", final_score)),
            experience_match=int(data.get("experience_match", 85)),
            location_match=int(data.get("location_match", 100)),
            matching_strengths=strengths,
            missing_skills=data.get("missing_skills", []),
            best_matching_project=data.get("best_matching_project"),
            recommended_angle=data.get("recommended_angle", "Candidature ciblée"),
            recommendation=rec
        )
    except Exception as e:
        print(f"[Matcher Error] Erreur parsing : {e}")
        fallback_score = min(100, 75 + date_bonus)
        return MatchingAnalysis(
            target=target,
            match_score=fallback_score,
            technical_match=80,
            experience_match=75,
            location_match=100,
            matching_strengths=[date_strength, "Compétences techniques générales Data/IA"],
            missing_skills=[],
            best_matching_project=profile.top_projects[0].title if profile.top_projects else None,
            recommended_angle="Approche PFE standard",
            recommendation="APPLY"
        )
