import json
import urllib.request
from typing import List, Dict, Any

try:
    from pfe_agent.models import ProjectHighlight
except ImportError:
    from models import ProjectHighlight

def sync_github_projects(username: str = "yousra-khallou") -> List[ProjectHighlight]:
    url = f"https://api.github.com/users/{username}/repos?sort=updated&per_page=10"
    headers = {"User-Agent": "PFE-Job-Hunter-Agent"}
    
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                
                projects = []
                for repo in data:
                    if repo.get("fork"):
                        continue
                        
                    name = repo.get("name", "Project")
                    desc = repo.get("description") or f"Dépôt GitHub {name} - Projets Data & IA"
                    lang = repo.get("language")
                    topics = repo.get("topics", [])
                    
                    tech_stack = []
                    if lang:
                        tech_stack.append(lang)
                    tech_stack.extend(topics[:4])
                    if not tech_stack:
                        tech_stack = ["Python", "Data & IA"]
                        
                    projects.append(ProjectHighlight(
                        title=f"{name} (GitHub)",
                        description=desc,
                        tech_stack=tech_stack
                    ))
                    
                return projects[:6]
    except Exception as e:
        print(f"[GitHub Sync Error] {e}")
        
    return []
