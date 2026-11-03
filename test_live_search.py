import os
import sys
import json
from ddgs import DDGS
from langchain_core.messages import SystemMessage, HumanMessage

try:
    from config import get_llm
except ImportError:
    from pfe_agent.config import get_llm

def test_live_extraction():
    d = DDGS()
    queries = [
        "stage PFE Data Maroc 2026",
        "stage PFE IA Maroc 2026",
        "stage PFE Data Engineer Casablanca 2026",
        "site:linkedin.com/posts stage PFE Data 2026",
        "site:rekrute.com stage PFE Data"
    ]
    
    collected_snippets = []
    seen_urls = set()
    
    for q in queries:
        try:
            results = list(d.text(q, max_results=3))
            for r in results:
                url = r.get("href", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    collected_snippets.append({
                        "title": r.get("title", ""),
                        "url": url,
                        "body": r.get("body", "")
                    })
        except Exception as e:
            pass
            
    print(f"Total collected raw snippets: {len(collected_snippets)}")
    
    # Send to LLM with strict instruction for active 2026/2027 campaign only
    llm = get_llm(temperature=0.2)
    prompt = f"""Voici des résultats bruts de recherche web en direct pour des offres de stage PFE Data & IA :
{json.dumps(collected_snippets[:8], ensure_ascii=False, indent=2)}

Extrais UNIQUEMENT les opportunités réelles et valides pour la campagne en cours (Stage PFE 2026 / 2027).
EXCLUS STRICTEMENT toute offre obsolète (datant de cycles passés comme Avril/Mai d'une année antérieure ou offres closes).

Pour chaque offre retenue, fournis au format JSON :
{{
  "targets": [
    {{
      "company_name": "...",
      "contact_email": "...",
      "contact_name": "...",
      "job_title": "...",
      "location": "...",
      "technologies_mentioned": ["..."],
      "raw_context": "...",
      "posted_date": "Date ou 'Campagne PFE 2026/2027'",
      "source_url": "URL directe",
      "source_platform": "LinkedIn / Rekrute / JobBoard / etc."
    }}
  ]
}}
Réponds STRICTEMENT avec l'objet JSON sans texte autour.
"""
    resp = llm.invoke([HumanMessage(content=prompt)])
    content = resp.content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    print("EXTRACTED TARGETS JSON:")
    print(content)

if __name__ == '__main__':
    test_live_extraction()
