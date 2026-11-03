import os
import sys
import json
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

# Add current and parent directory to sys.path
current_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(current_dir.parent))

try:
    from pfe_agent.models import CandidateProfile
    from pfe_agent.graph import build_pfe_agent_graph
except ImportError:
    from models import CandidateProfile
    from graph import build_pfe_agent_graph

console = Console()

def load_profile() -> CandidateProfile:
    profile_path = current_dir / "profile_data.json"
    if not profile_path.exists():
        console.print("[bold red]Fichier profile_data.json introuvable ![/bold red]")
        sys.exit(1)
    with open(profile_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return CandidateProfile(**data)

SAMPLE_LINKEDIN_POST = """
📢 #RECRUTEMENT #STAGE_PFE 2027

Nous recherchons pour nos équipes plusieurs profils stagiaires PFE :
1. Capgemini Engineering (Casablanca / Rabat) :
Stagiaire Data Engineer & IA / LLM. Stack : Apache Spark, Kafka, FastAPI, Qdrant, RAG, Docker.
Envoyez vos CV à : recruitment.maroc@capgemini.com (Réf : PFE-DATA-IA-2027)

2. Devoteam Digital :
Recherche Stagiaires PFE Data Platform & ETL. Stack : Apache Airflow, dbt, MinIO, PostgreSQL, Power BI.
Contact RH : fatima.zahra.rh@devoteam.com

3. Startup FinTech X :
Recherche un(e) élève ingénieur(e) pour concevoir un pipeline de streaming temps réel et monitoring.
Contactez directement notre CTO à : tech-lead@fintech-x.io
"""

def main():
    console.print(Panel.fit(
        "[bold cyan]🎯 Agent IA Chasseur de PFE (LangGraph + NVIDIA AI)[/bold cyan]\n"
        "[italic]Extraction intelligente, scoring sémantique et candidatures sur-mesure[/italic]",
        border_style="cyan"
    ))
    
    # 1. Vérification clé API
    env_file = current_dir / ".env"
    if not env_file.exists():
        console.print("[yellow]⚠️ Fichier .env non trouvé dans pfe_agent/. Création du fichier...[/yellow]")
        api_key = Prompt.ask("[bold green]Entrez votre clé API NVIDIA (commence par nvapi-...)[/bold green]")
        with open(env_file, "w", encoding="utf-8") as f:
            f.write(f"NVIDIA_API_KEY={api_key.strip()}\n")
            f.write("NVIDIA_MODEL=meta/llama-3.3-70b-instruct\n")
        console.print("[green]✓ Clé enregistrée avec succès dans .env ![/green]\n")
        
    profile = load_profile()
    console.print(f"[bold green]✓ Profil chargé :[/bold green] {profile.full_name} ({profile.title})")
    console.print(f"[dim]Disponibilité : {profile.availability_date} | Durée : {profile.desired_duration}[/dim]")
    console.print(f"[dim]Projets référencés : {', '.join(p.title for p in profile.top_projects[:3])}...[/dim]\n")
    
    # 2. Choix de l'entrée
    console.print("[bold]Options d'analyse :[/bold]")
    console.print("1. Tester avec le post LinkedIn de démonstration (Capgemini, Devoteam, FinTech)")
    console.print("2. Coller mon propre post / texte contenant des emails RH")
    
    choice = Prompt.ask("Votre choix", choices=["1", "2"], default="1")
    
    if choice == "1":
        raw_text = SAMPLE_LINKEDIN_POST
        console.print("\n[dim]--- Post de démonstration sélectionné ---[/dim]")
    else:
        console.print("\n[bold yellow]Collez votre texte ci-dessous (tapez 'FIN' sur une nouvelle ligne quand vous avez terminé) :[/bold yellow]")
        lines = []
        while True:
            try:
                line = input()
                if line.strip().upper() == "FIN":
                    break
                lines.append(line)
            except EOFError:
                break
        raw_text = "\n".join(lines)
        if not raw_text.strip():
            console.print("[red]Texte vide. Annulation.[/red]")
            return

    # 3. Exécution du graphe LangGraph
    console.print("\n[bold cyan]🚀 Lancement du workflow LangGraph...[/bold cyan]")
    
    with console.status("[bold green]Agent en cours d'analyse (Extraction -> Matching -> Rédaction)...[/bold green]"):
        app = build_pfe_agent_graph()
        initial_state = {
            "raw_input_text": raw_text,
            "profile": profile,
            "min_score_threshold": 50,
            "extracted_targets": [],
            "match_results": [],
            "applications": [],
            "error": ""
        }
        final_state = app.invoke(initial_state)

    applications = final_state.get("applications", [])
    extracted_targets = final_state.get("extracted_targets", [])
    
    console.print(f"\n[bold green]✓ Analyse terminée :[/bold green] {len(extracted_targets)} cible(s) extraite(s), {len(applications)} candidature(s) générée(s).\n")
    
    # 4. Tableau récapitulatif
    table = Table(title="📊 Tableau de bord des opportunités détectées", show_header=True, header_style="bold magenta")
    table.add_column("Entreprise", style="bold")
    table.add_column("Poste / Domaine")
    table.add_column("Email Contact", style="cyan")
    table.add_column("Score Match", justify="center")
    table.add_column("Projet Sélectionné", style="green")
    
    for app_item in applications:
        score = app_item.matching.match_score
        score_color = "green" if score >= 80 else "yellow" if score >= 65 else "red"
        table.add_row(
            app_item.target.company_name,
            app_item.target.job_title or "PFE Data/IA",
            app_item.target.contact_email,
            f"[{score_color}]{score}%[/{score_color}]",
            app_item.matching.best_matching_project or "-"
        )
    console.print(table)
    
    # 5. Affichage des emails rédigés
    for i, app_item in enumerate(applications, 1):
        console.print("\n" + "="*80)
        console.print(f"[bold yellow]📧 CANDIDATURE #{i} : {app_item.target.company_name} ({app_item.target.contact_email})[/bold yellow]")
        console.print(f"[bold]Objet :[/bold] {app_item.subject_line}")
        console.print(f"[bold]Angle stratégique :[/bold] [italic]{app_item.matching.recommended_angle}[/italic]\n")
        
        console.print(Panel(
            app_item.email_body,
            title=f"Brouillon Email Sur-Mesure",
            border_style="green"
        ))

    # 6. Sauvegarde des résultats
    output_path = current_dir / "candidatures_generees.json"
    with open(output_path, "w", encoding="utf-8") as f:
        export_data = [a.model_dump() for a in applications]
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    console.print(f"\n[dim]💾 Toutes les candidatures ont été sauvegardées dans : {output_path}[/dim]\n")

if __name__ == "__main__":
    main()
