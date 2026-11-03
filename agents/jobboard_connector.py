import logging
from typing import List

try:
    from pfe_agent.models import RecruiterTarget
    from pfe_agent.agents.web_search_engine import search_live_web_snippets, parse_snippets_to_targets
except ImportError:
    from models import RecruiterTarget
    from agents.web_search_engine import search_live_web_snippets, parse_snippets_to_targets

logger = logging.getLogger("JobboardConnector")

def crawl_abg_jobboard() -> List[RecruiterTarget]:
    """Crawl live job boards (ABG, Rekrute, Emploi.ma, WTTJ, Dreamjob, PFE Daba) for fresh PFE stages."""
    queries = [
        "site:rekrute.com stage PFE Data 2026",
        "site:dreamjob.ma stage PFE Data 2026",
        "site:pfedaba.ma Data Engineer",
        "site:abg.asso.fr stage Data IA 2026",
        "site:welcometothejungle.com stage Data Engineering 2026"
    ]
    
    logger.info(f"Lancement du scan Job Boards Live avec {len(queries)} requêtes...")
    snippets = search_live_web_snippets(queries, max_per_query=3)
    
    targets = parse_snippets_to_targets(
        snippets=snippets, 
        context_type="Job Board / Plateforme Stage", 
        keywords=["Data Engineering", "IA", "LLM", "Stage PFE"]
    )
    
    return targets
