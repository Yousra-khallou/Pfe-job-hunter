import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class ApplicationStatus(str, Enum):
    TO_EXAMINE = "a_examiner"         # À examiner
    TO_APPLY = "a_postuler"           # À postuler
    SUBMITTED = "candidature_envoyee" # Candidature envoyée
    REJECTED = "refuse"               # Refus
    # Rétrocompatibilité
    READY_TO_SEND = "a_valider"
    DISCOVERED = "decouvert"
    ANALYZING = "analyse_en_cours"
    MATCHED = "evalue"
    VERIFIED = "verifie"
    FOLLOW_UP = "relance"

class AuditActionType(str, Enum):
    SEARCH = "recherche_offres"
    EXTRACTION = "extraction_cible"
    RESEARCH = "intelligence_entreprise"
    MATCHING = "scoring_semantique"
    DRAFTING = "redaction_sur_mesure"
    AUTOFILL = "formulaire_autofill"
    APPROVAL = "validation_humaine"
    DISPATCH = "soumission_candidature"
    VERIFICATION = "verification_soumission"

class AuditLogEntry(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    agent_name: str = Field(description="Nom de l'agent qui a exécuté l'action")
    action: AuditActionType = Field(description="Type d'action réalisée")
    description: str = Field(description="Détail lisible de l'action")
    target_company: Optional[str] = Field(default=None, description="Entreprise ciblée")
    status: str = Field(default="succes", description="succes | avertissement | erreur")

class ApplicationPersonalizationConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    enabled: bool = Field(default=True, description="Activer le module de personnalisation")
    master_cv_path: str = Field(default="Applications/main.md", description="Chemin du CV maître (Markdown)")
    master_cv_pdf_path: str = Field(default="Applications/cv_maitre.pdf", description="Chemin du CV maître (PDF)")
    master_profile_path: str = Field(default="profile_data.json", description="Chemin du profil maître JSON")
    cv_format: str = Field(default="latex_and_pdf", description="Format de sortie du CV")
    cv_max_pages: int = Field(default=1, description="Nombre de pages maximum du CV")
    generate_tailored_cv: bool = Field(default=True, description="Générer un CV adapté par offre")
    generate_motivation_letter: bool = Field(default=True, description="Générer une lettre de motivation adaptée")
    letter_format: str = Field(default="pdf", description="Format de la lettre")
    save_editable_letter: bool = Field(default=True, description="Conserver une version modifiable")
    customize_headline: bool = Field(default=True, description="Adapter le titre selon l'offre")
    customize_summary: bool = Field(default=True, description="Adapter le profil selon l'offre")
    reorder_experiences: bool = Field(default=True, description="Réordonner les expériences selon l'offre")
    reorder_projects: bool = Field(default=True, description="Sélectionner et réordonner les projets selon l'offre")
    match_skills_to_offer: bool = Field(default=True, description="Prioriser les compétences de l'offre")
    preserve_verified_facts: bool = Field(default=True, description="Préserver strictement les faits vérifiés du CV maître")
    require_fact_validation: bool = Field(default=True, description="Interdire toute hallucination de compétence")
    generate_application_email: bool = Field(default=True, description="Générer l'email d'accompagnement")
    require_human_approval: bool = Field(default=True, description="Exiger validation humaine avant envoi")
    auto_submit_applications: bool = Field(default=False, description="Envoi automatique désactivé")
    output_directory: str = Field(default="applications/", description="Dossier de sortie des candidatures")

class SearchConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    keywords: List[str] = Field(default_factory=lambda: ["Data Engineer", "IA / LLM", "PySpark", "Stage PFE"], description="Mots-clés de recherche")
    locations: List[str] = Field(default_factory=lambda: ["Casablanca", "Rabat", "Maroc", "Remote"], description="Villes ou zones de recherche")
    target_contract_types: List[str] = Field(default_factory=lambda: ["Stage PFE", "Pré-embauche"], description="Types de contrat recherchés")
    target_companies: List[str] = Field(default_factory=lambda: ["Capgemini", "Thales", "Orange", "Inetum", "DXC Technology", "DATAPROTECT", "Leyton", "Société Générale"], description="Entreprises ciblées en priorité")
    target_linkedin_urls: List[str] = Field(default_factory=list, description="Pages LinkedIn d'entreprises ou sites carrières à surveiller")
    auto_scan_enabled: bool = Field(default=True, description="Activation du scan périodique automatique")
    scan_interval_hours: int = Field(default=4, description="Intervalle de scan automatique en heures")
    min_match_score: int = Field(default=50, description="Score minimum pour retenir une candidature")
    target_start_date: str = Field(default="Janvier 2027", description="Date cible de début de stage")
    prioritize_january_2027: bool = Field(default=True, description="Prioriser les offres de Janvier 2027 tout en conservant les dates flexibles")
    application_personalization: ApplicationPersonalizationConfig = Field(default_factory=ApplicationPersonalizationConfig, description="Paramètres de personnalisation sur-mesure")

class ProjectHighlight(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    title: str = Field(description="Nom du projet réalisé")
    description: str = Field(description="Résumé court de ce qui a été développé et l'impact")
    tech_stack: List[str] = Field(description="Technologies utilisées")

class CandidateProfile(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    full_name: str = Field(description="Nom et prénom du candidat")
    title: str = Field(description="Titre du profil (ex: Élève Ingénieure en Data Engineering & IA)")
    email: str = Field(description="Email de contact")
    phone: Optional[str] = Field(default=None, description="Numéro de téléphone")
    location: Optional[str] = Field(default="Maroc (Mobilité internationale)", description="Localisation / Mobilité")
    linkedin_url: Optional[str] = Field(default="https://www.linkedin.com/in/yousra-khallou", description="Lien profil LinkedIn")
    github_url: Optional[str] = Field(default="https://github.com/yousra-khallou", description="Lien GitHub")
    portfolio_url: Optional[str] = Field(default=None, description="Lien Portfolio")
    sample_cover_letter: Optional[str] = Field(default="", description="Exemple ou modèle de lettre de motivation de référence")
    raw_cv_text: Optional[str] = Field(default="", description="Texte brut ou structure du CV de référence")
    pfe_topics_sought: List[str] = Field(default_factory=list, description="Thématiques ou sujets de PFE recherchés")
    key_skills: List[str] = Field(default_factory=list, description="Compétences techniques clés")
    top_projects: List[ProjectHighlight] = Field(default_factory=list, description="Liste des projets phares à valoriser")
    desired_duration: str = Field(default="6 mois", description="Durée de stage PFE")
    availability_date: str = Field(default="Janvier 2027", description="Période de début")

class RecruiterTarget(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_name: str = Field(description="Nom de l'entreprise")
    contact_email: str = Field(description="Email RH ou contact")
    contact_name: Optional[str] = Field(default="Responsable Recrutement", description="Nom du contact ou RH si mentionné")
    job_title: Optional[str] = Field(default="Stage PFE Data & IA", description="Intitulé du poste")
    location: Optional[str] = Field(default="Non spécifié", description="Ville ou pays")
    technologies_mentioned: List[str] = Field(default_factory=list, description="Technologies citées")
    raw_context: str = Field(default="", description="Extrait du texte source")
    posted_date: Optional[str] = Field(default="Campagne PFE 2026/2027 (Récente)", description="Date de publication ou fraîcheur de l'offre")
    start_date: Optional[str] = Field(default="Janvier 2027 (Flexible)", description="Date de début du stage (ex: Janvier 2027, Février 2027, Flexible)")
    source_url: Optional[str] = Field(default=None, description="Lien direct vers l'offre / post original")
    source_platform: Optional[str] = Field(default="Web / LinkedIn Live", description="Plateforme source de détection")

class CompanyResearch(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    company_name: str = Field(description="Nom de l'entreprise")
    industry: str = Field(default="Technologies & Data", description="Secteur d'activité principal")
    tech_culture_summary: str = Field(default="Entreprise orientée données et innovation IA", description="Culture technique")
    key_products_or_clients: List[str] = Field(default_factory=list, description="Projets clés ou clients")
    values_and_vision: str = Field(default="Excellence technique et transformation digitale", description="Vision et valeurs")

class FormAutofillPayload(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    full_name: str = Field(description="Nom complet")
    email: str = Field(description="Adresse email")
    phone: str = Field(description="Numéro de téléphone")
    location: str = Field(description="Ville & Pays")
    linkedin_url: str = Field(description="URL LinkedIn")
    github_url: str = Field(description="URL GitHub")
    availability: str = Field(description="Date de disponibilité")
    expected_duration: str = Field(description="Durée souhaitée")
    why_us_answer: str = Field(description="Réponse à 'Pourquoi souhaitez-vous nous rejoindre ?'")
    top_skill_highlight: str = Field(description="Réponse à 'Quelle est votre principale compétence ?'")
    custom_form_answers: Dict[str, str] = Field(default_factory=dict, description="Champs personnalisés de formulaire web")

class VerificationResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    is_verified: bool = Field(default=True, description="Statut de vérification")
    verification_message: str = Field(default="Candidature enregistrée et vérifiée par l'Agent IA", description="Preuve / Détails de confirmation")
    verification_timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="Date/heure de vérification")
    proof_type: str = Field(default="HTTP Dispatch Confirmation", description="Type de preuve (Mailto/HTTP/Browser)")

class EpisodicMemoryItem(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = Field(description="ID de la candidature")
    company_name: str = Field(description="Nom de l'entreprise")
    portal_type: str = Field(default="Email Direct / Formulaire Web", description="Canal de candidature")
    lessons_learned: str = Field(description="Leçons ou remarques enregistrées par l'agent")
    applied_date: str = Field(default_factory=lambda: datetime.now().isoformat())

class MatchingAnalysis(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    target: Any = Field(description="Cible recruteur analysée")
    match_score: int = Field(description="Score de pertinence de 0 à 100")
    technical_match: int = Field(default=90, description="Score d'alignement technique (0-100)")
    experience_match: int = Field(default=85, description="Score d'alignement séniorité/formation (0-100)")
    location_match: int = Field(default=100, description="Score d'alignement localisation/remote (0-100)")
    matching_strengths: List[str] = Field(default_factory=list, description="Points forts de concordance")
    missing_skills: List[str] = Field(default_factory=list, description="Compétences manquantes identifiées")
    best_matching_project: Optional[str] = Field(default=None, description="Projet du candidat le plus pertinent à citer")
    recommended_angle: str = Field(default="Candidature ciblée", description="Angle d'attaque personnalisé")
    recommendation: str = Field(default="APPLY", description="Recommandation finale: APPLY | REVIEW | REJECT")

class GeneratedApplication(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target: Any = Field(description="Cible recruteur")
    matching: Any = Field(description="Résultat du matching")
    company_research: Optional[CompanyResearch] = Field(default=None, description="Enrichissement intelligence entreprise")
    subject_line: str = Field(description="Objet d'email percutant")
    email_body: str = Field(description="Corps de l'email rédigé sur-mesure")
    cover_letter_snippet: Optional[str] = Field(default=None, description="Lettre d'accompagnement sur-mesure")
    tailored_cv_summary: Optional[str] = Field(default=None, description="Profil et compétences du CV adaptés spécifiquement pour cette offre")
    folder_path: Optional[str] = Field(default=None, description="Dossier dédié de la candidature (ex: applications/capgemini_data_ia)")
    tailored_cv_pdf: Optional[str] = Field(default=None, description="Chemin du CV personnalisé PDF")
    tailored_cv_tex: Optional[str] = Field(default=None, description="Chemin du CV personnalisé LaTeX")
    tailored_letter_pdf: Optional[str] = Field(default=None, description="Chemin de la lettre personnalisée PDF")
    tailored_letter_md: Optional[str] = Field(default=None, description="Chemin de la lettre modifiable Markdown")
    offer_analysis: Optional[Dict[str, Any]] = Field(default=None, description="Analyse détaillée de l'offre retenue")
    autofill_payload: Optional[FormAutofillPayload] = Field(default=None, description="Payload de pré-remplissage formulaire web")
    verification: Optional[VerificationResult] = Field(default=None, description="Preuve et résultat de vérification")
    status: ApplicationStatus = Field(default=ApplicationStatus.TO_EXAMINE, description="Statut: a_examiner | a_postuler | candidature_envoyee | refuse")
    applied_at: Optional[str] = Field(default=None, description="Date de candidature enregistrée (ISO)")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    notes: Optional[str] = Field(default="", description="Notes personnelles du candidat")
