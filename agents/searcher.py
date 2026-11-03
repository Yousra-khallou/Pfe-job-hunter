import logging
from typing import List

try:
    from pfe_agent.models import RecruiterTarget, SearchConfig
    from pfe_agent.agents.web_search_engine import search_live_web_snippets, parse_snippets_to_targets
except ImportError:
    from models import RecruiterTarget, SearchConfig
    from agents.web_search_engine import search_live_web_snippets, parse_snippets_to_targets

logger = logging.getLogger("AutomatedSearcher")

def generate_automated_search_targets(search_config: SearchConfig) -> List[RecruiterTarget]:
    """Exécute une recherche web en direct basée sur les critères de SearchConfig et filtre les offres obsolètes."""
    kw_str = " ".join(search_config.keywords[:3]) if search_config.keywords else "Data Engineer IA"
    loc_list = search_config.locations[:2] if search_config.locations else ["Maroc", "France"]
    
    queries = []
    
    # 1. Recherche ciblée sur les entreprises prioritaires
    target_comps = getattr(search_config, "target_companies", [])
    for comp in target_comps[:4]:
        queries.append(f'site:linkedin.com/posts "{comp}" stage PFE Data 2026')
        queries.append(f'"{comp}" recrutement stage PFE Data 2026')
        
    # 2. Recherche par mots-clés et localisations
    for loc in loc_list:
        queries.append(f"stage PFE {kw_str} {loc} 2026")
        queries.append(f"site:linkedin.com/posts stage PFE {kw_str} {loc} 2026")
    
    logger.info(f"Lancement de la recherche automatisée en direct avec {len(queries)} requêtes ciblées...")
    snippets = search_live_web_snippets(queries, max_per_query=3)
    
    targets = parse_snippets_to_targets(
        snippets=snippets,
        context_type="Veille Web Automatique",
        keywords=search_config.keywords
    )
    
    return targets
