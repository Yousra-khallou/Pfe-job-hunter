import time
import threading
from datetime import datetime
from typing import Callable

try:
    from pfe_agent.models import SearchConfig, AuditActionType
    from pfe_agent.storage import StorageManager
    from pfe_agent.agents.searcher import generate_automated_search_targets
    from pfe_agent.graph import build_pfe_agent_graph
except ImportError:
    from models import SearchConfig, AuditActionType
    from storage import StorageManager
    from agents.searcher import generate_automated_search_targets
    from graph import build_pfe_agent_graph

class AutonomousScheduler:
    def __init__ (self):
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("[Scheduler] Service de veille autonome démarré en arrière-plan.")

    def stop(self):
        self._running = False
        print("[Scheduler] Service de veille arrêté.")

    def _run_loop(self):
        while self._running:
            try:
                config = StorageManager.get_search_config()
                if config.auto_scan_enabled:
                    print("[Scheduler] Exécution d'un scan automatique d'offres...")
                    StorageManager.add_audit_log(
                        agent_name="AutonomousScheduler",
                        action=AuditActionType.SEARCH,
                        description=f"Lancement de la recherche périodique automatique ({', '.join(config.keywords[:2])})."
                    )
                    
                    targets = generate_automated_search_targets(config)
                    if targets:
                        profile = StorageManager.get_profile()
                        langgraph_app = build_pfe_agent_graph()
                        
                        raw_text_sim = "\n\n".join([
                            f"Entreprise : {t.company_name} ({t.location})\nPoste : {t.job_title}\nEmail : {t.contact_email}\nTechnos : {', '.join(t.technologies_mentioned)}\nContexte : {t.raw_context}"
                            for t in targets
                        ])
                        
                        initial_state = {
                            "raw_input_text": raw_text_sim,
                            "profile": profile,
                            "min_score_threshold": config.min_match_score,
                            "extracted_targets": targets,
                            "company_researches": {},
                            "match_results": [],
                            "applications": [],
                            "error": ""
                        }
                        
                        final_state = langgraph_app.invoke(initial_state)
                        generated_apps = final_state.get("applications", [])
                        added = StorageManager.add_applications(generated_apps)
                        
                        StorageManager.add_audit_log(
                            agent_name="AutonomousScheduler",
                            action=AuditActionType.SEARCH,
                            description=f"Scan terminé : {len(targets)} opportunités trouvées, {len(added)} nouvelles candidatures ajoutées au dashboard."
                        )
                
                # Sleep interval based on config (ex: 4 hours = 14400s, minimum 30 minutes)
                sleep_seconds = max(config.scan_interval_hours * 3600, 1800)
                time.sleep(sleep_seconds)
            except Exception as e:
                print(f"[Scheduler Error] Erreur durant la veille : {e}")
                time.sleep(300)

scheduler_service = AutonomousScheduler()
