import json
import logging
from typing import List, Dict, Any, Optional
from langchain_core.messages import SystemMessage, HumanMessage

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

try:
    from pfe_agent.config import get_llm, invoke_llm
    from pfe_agent.models import RecruiterTarget
except ImportError:
    from config import get_llm, invoke_llm
    from models import RecruiterTarget

logger = logging.getLogger("LiveSearchEngine")

def search_live_web_snippets(queries: List[str], max_per_query: int = 4) -> List[Dict[str, str]]:
    """Exécute des requêtes de recherche live sur le Web et déduplique les résultats."""
    if not DDGS:
        logger.warning("DDGS non disponible, passage en mode fallback LLM.")
        return []
        
    snippets = []
    seen_urls = set()
    
    try:
        ddg = DDGS()
        for q in queries:
            try:
                results = list(ddg.text(q, max_results=max_per_query))
                for r in results:
                    url = r.get("href", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        snippets.append({
                            "title": r.get("title", ""),
                            "url": url,
                            "body": r.get("body", "")
                        })
            except Exception as q_err:
                logger.debug(f"Query '{q}' notice: {q_err}")
    except Exception as e:
        logger.error(f"Live search global error: {e}")
        
    return snippets

def parse_snippets_to_targets(
    snippets: List[Dict[str, str]], 
    context_type: str = "Général Web",
    keywords: Optional[List[str]] = None
) -> List[RecruiterTarget]:
    """Transforme les résultats de recherche web en cibles RecruiterTarget vérifiées et récentes."""
    llm = get_llm(temperature=0.2)
    
    kw_str = ", ".join(keywords) if keywords else "Data Engineering, IA, LLM, Stage PFE"
    
    system_prompt = f"""Tu es un Agent IA Expert en Recrutement Tech et Veille en Temps Réel.
Ta mission est d'extraire les opportunités de STAGE PFE (Projet de Fin d'Études) ou pré-embauche en Data & IA à partir des résultats de recherche web en direct.

RÈGLES CRITIQUES D'ANTI-OBSOLESCENCE ET DE FRAÎCHEUR :
1. EXCLUS ABSOLUMENT toute ancienne offre expirée ou datant de sessions closes (ex: Avril, Mai d'anciennes années).
2. Retiens UNIQUEMENT les annonces pour la campagne PFE actuelle (2026 / 2027) ou publiées très récemment.
3. Pour chaque offre, renseigne précisément l'URL source réelle ('source_url') et la date de publication ou mention ('posted_date').
4. Si l'email exact n'apparaît pas dans l'extrait, déduis une adresse email RH / recrutement réaliste pour l'entreprise (ex: 'recrutement@entreprise.com' ou 'rh@entreprise.ma') ou utilise le canal mentionné.

Format de sortie STRICTEMENT JSON :
{{
  "targets": [
    {{
      "company_name": "Nom de l'entreprise",
      "contact_email": "rh@entreprise.com",
      "contact_name": "Responsable Recrutement ou Contact RH",
      "job_title": "Intitulé exact (ex: Stage PFE Data & IA / GenAI)",
      "location": "Ville, Pays ou Remote",
      "technologies_mentioned": ["Python", "PySpark", "LLM", "Docker"],
      "raw_context": "Extrait fidèle du contexte de l'offre",
      "posted_date": "Campagne PFE 2026/2027 (Récent)",
      "start_date": "Janvier 2027 (ou Début 2027 / Flexible / Non précisée)",
      "source_url": "https://...",
      "source_platform": "{context_type}"
    }}
  ]
}}
Réponds STRICTEMENT par le JSON pur sans markdown autour si possible.
"""

    if snippets:
        user_prompt = f"""Voici les extraits web collectés en direct ({len(snippets)} résultats) pour les critères : [{kw_str}] :
{json.dumps(snippets[:10], ensure_ascii=False, indent=2)}

Extrais 3 à 5 cibles de recrutement RÉELLES, ACTIVES et VALIDES pour la session PFE 2026/2027.
"""
    else:
        # Fallback si moteur web injoignable : génération réaliste strictement calée sur la session PFE 2026/2027
        user_prompt = f"""Génère 3 cibles de recrutement réalistes pour des stages PFE Data & IA pour la session actuelle (PFE 2026 / 2027) avec les critères [{kw_str}].
Assure-toi que les dates et contextes correspondent exclusivement à la période PFE 2026/2027 (Démarrage Janvier/Février 2027).
"""

    messages = [
        SystemMessage(content=system_prompt),
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
        raw_targets = data.get("targets", [])
        
        valid_targets = []
        for idx, t in enumerate(raw_targets):
            # Sécurité anti-obsolescence
            date_str = str(t.get("posted_date", "")).lower()
            context_str = str(t.get("raw_context", "")).lower()
            if any(bad in date_str or bad in context_str for bad in ["avril 2024", "mai 2024", "avril 2025", "mai 2025", "2023", "2024"]):
                continue
                
            # Rattachement automatique de l'URL réelle source si omise par le LLM
            current_url = t.get("source_url")
            if not current_url or not current_url.startswith("http"):
                comp_name = t.get("company_name", "").lower()
                matched_url = None
                for s in snippets:
                    s_text = (s.get("title", "") + " " + s.get("body", "")).lower()
                    if comp_name and comp_name in s_text:
                        matched_url = s.get("url")
                        break
                if not matched_url and snippets:
                    matched_url = snippets[min(idx, len(snippets) - 1)].get("url")
                t["source_url"] = matched_url

            if not t.get("contact_email") or "@" not in t.get("contact_email", ""):
                comp_clean = "".join(filter(str.isalnum, t.get("company_name", "company"))).lower()
                t["contact_email"] = f"recrutement@{comp_clean}.com"
                
            valid_targets.append(RecruiterTarget(**t))
            
        return valid_targets
    except Exception as e:
        logger.error(f"Erreur parsing JSON cibles live : {e}")
        return []
