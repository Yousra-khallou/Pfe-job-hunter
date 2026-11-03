import logging
from typing import List

try:
    from pfe_agent.models import RecruiterTarget
    from pfe_agent.agents.web_search_engine import search_live_web_snippets, parse_snippets_to_targets
except ImportError:
    from models import RecruiterTarget
    from agents.web_search_engine import search_live_web_snippets, parse_snippets_to_targets

logger = logging.getLogger("LinkedInConnector")

def crawl_linkedin_feed(keywords: List[str] = None) -> List[RecruiterTarget]:
    """Crawl live LinkedIn posts and recruitment feeds for recent PFE stage opportunities."""
    kw_list = keywords or ["Data Engineer", "Intelligence Artificielle", "LLM", "PySpark"]
    kw_str = " ".join(kw_list[:3])
    
    # Requêtes réelles ciblées sur les posts LinkedIn récents et la campagne PFE en cours
    queries = [
        f"site:linkedin.com/posts stage PFE {kw_str} Maroc 2026",
        f"site:linkedin.com/posts stage PFE Data IA Casablanca 2026",
        f"site:linkedin.com/posts #RECRUTEMENT #STAGE_PFE Data 2026",
        f"site:linkedin.com/posts stage PFE Data France Remote 2026"
    ]
    
    logger.info(f"Lancement de la recherche LinkedIn Live avec {len(queries)} requêtes...")
    snippets = search_live_web_snippets(queries, max_per_query=3)
    
    targets = parse_snippets_to_targets(
        snippets=snippets, 
        context_type="LinkedIn Live Post", 
        keywords=kw_list
    )
    
    return targets
