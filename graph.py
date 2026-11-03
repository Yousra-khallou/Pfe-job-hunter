import time
from typing import List, Dict, Any
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

try:
    from pfe_agent.models import CandidateProfile, RecruiterTarget, MatchingAnalysis, CompanyResearch, FormAutofillPayload, GeneratedApplication, AuditActionType
    from pfe_agent.agents.extractor import extract_recruiter_targets
    from pfe_agent.agents.matcher import match_candidate_with_target
    from pfe_agent.agents.copywriter import generate_tailored_application
    from pfe_agent.agents.researcher import research_company_target
    from pfe_agent.agents.autofill import generate_form_autofill_payload
    from pfe_agent.storage import StorageManager
except ImportError:
    from models import CandidateProfile, RecruiterTarget, MatchingAnalysis, CompanyResearch, FormAutofillPayload, GeneratedApplication, AuditActionType
    from agents.extractor import extract_recruiter_targets
    from agents.matcher import match_candidate_with_target
    from agents.copywriter import generate_tailored_application
    from agents.researcher import research_company_target
    from agents.autofill import generate_form_autofill_payload
    from storage import StorageManager

class AgentState(TypedDict):
    raw_input_text: str
    profile: CandidateProfile
    min_score_threshold: int
    extracted_targets: List[RecruiterTarget]
    company_researches: Dict[str, CompanyResearch]
    match_results: List[MatchingAnalysis]
    applications: List[GeneratedApplication]
    error: str

def extract_node(state: AgentState) -> Dict[str, Any]:
    existing_targets = state.get("extracted_targets", [])
    if existing_targets:
        return {"extracted_targets": existing_targets}
        
    raw_text = state.get("raw_input_text", "")
    targets = extract_recruiter_targets(raw_text)
    StorageManager.add_audit_log(
        agent_name="ExtractorAgent",
        action=AuditActionType.EXTRACTION,
        description=f"Extraction de {len(targets)} cible(s) recruteur à partir du texte source."
    )
    return {"extracted_targets": targets}

def research_node(state: AgentState) -> Dict[str, Any]:
    targets = state.get("extracted_targets", [])
    researches: Dict[str, CompanyResearch] = {}
    for target in targets:
        try:
            comp_name = target.company_name if hasattr(target, "company_name") else target.get("company_name", "Unknown")
            res = research_company_target(target)
            researches[comp_name] = res
            StorageManager.add_audit_log(
                agent_name="ResearcherAgent",
                action=AuditActionType.RESEARCH,
                description=f"Intelligence entreprise générée pour {comp_name} ({res.industry}).",
                target_company=comp_name
            )
            time.sleep(0.5)
        except Exception as e:
            print(f"[Researcher Error] {e}")
    return {"company_researches": researches}

def match_node(state: AgentState) -> Dict[str, Any]:
    targets = state.get("extracted_targets", [])
    profile = state.get("profile")
    
    matches: List[MatchingAnalysis] = []
    for target in targets:
        try:
            analysis = match_candidate_with_target(target, profile)
            matches.append(analysis)
            comp_name = target.company_name if hasattr(target, "company_name") else target.get("company_name", "Unknown")
            StorageManager.add_audit_log(
                agent_name="MatcherAgent",
                action=AuditActionType.MATCHING,
                description=f"Scoring sémantique calculé : {analysis.match_score}% de pertinence pour {comp_name}.",
                target_company=comp_name
            )
            time.sleep(0.5)
        except Exception as e:
            print(f"[Matcher Error] {e}")
        
    matches.sort(key=lambda x: x.match_score, reverse=True)
    return {"match_results": matches}

def draft_and_autofill_node(state: AgentState) -> Dict[str, Any]:
    matches = state.get("match_results", [])
    profile = state.get("profile")
    researches = state.get("company_researches", {})
    threshold = state.get("min_score_threshold", 50)
    
    applications: List[GeneratedApplication] = []
    for match in matches:
        if match.match_score >= threshold:
            try:
                app = generate_tailored_application(match, profile)
                
                target_dict = match.target.model_dump() if hasattr(match.target, "model_dump") else match.target
                comp_name = target_dict.get("company_name", "Entreprise")
                research = researches.get(comp_name) or research_company_target(match.target)
                
                autofill = generate_form_autofill_payload(profile, match.target, match, research)
                
                app.company_research = research
                app.autofill_payload = autofill
                applications.append(app)
                
                StorageManager.add_audit_log(
                    agent_name="Copywriter & Autofill Agent",
                    action=AuditActionType.DRAFTING,
                    description=f"Rédaction sur-mesure et payload d'auto-remplissage formulaire générés pour {comp_name}.",
                    target_company=comp_name
                )
                time.sleep(0.5)
            except Exception as e:
                print(f"[Draft Error] {e}")
            
    return {"applications": applications}

def build_pfe_agent_graph():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("extract", extract_node)
    workflow.add_node("research", research_node)
    workflow.add_node("match", match_node)
    workflow.add_node("draft_autofill", draft_and_autofill_node)
    
    workflow.add_edge(START, "extract")
    workflow.add_edge("extract", "research")
    workflow.add_edge("research", "match")
    workflow.add_edge("match", "draft_autofill")
    workflow.add_edge("draft_autofill", END)
    
    return workflow.compile()
