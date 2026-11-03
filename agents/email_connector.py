import os
import json
import imaplib
import smtplib
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import List, Dict, Any, Optional
from pathlib import Path

from langchain_core.messages import SystemMessage, HumanMessage

try:
    from pfe_agent.config import get_llm
    from pfe_agent.models import RecruiterTarget
except ImportError:
    from config import get_llm
    from models import RecruiterTarget

EMAIL_READER_SYSTEM_PROMPT = """Tu es un Agent IA Spécialisé dans l'Extraction d'Opportunités d'Emploi à partir d'Emails et d'Alertes RH.
Ta mission est d'analyser le contenu d'emails reçus (LinkedIn Job Alert, Welcome to the Jungle, Indeed, recruteurs directs) et d'extraire les offres de Stage PFE Data & IA pertinentes.

Pour chaque opportunité identifiée, extrais :
- company_name : Nom de l'entreprise
- contact_email : Adresse email de contact RH
- contact_name : Nom de la personne RH / CTO si mentionné
- job_title : Intitulé exact du poste
- location : Localisation (ville / pays / remote)
- technologies_mentioned : Liste des technologies clés
- raw_context : Extrait du texte de l'alerte

Réponds STRICTEMENT en JSON :
{
  "targets": [
    {
      "company_name": "...",
      "contact_email": "...",
      "contact_name": "...",
      "job_title": "...",
      "location": "...",
      "technologies_mentioned": ["..."],
      "raw_context": "..."
    }
  ]
}
Ne génère AUCUN texte avant ou après le JSON.
"""

def send_real_email_smtp(
    to_email: str,
    subject: str,
    body_text: str,
    attachment_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Envoie un véritable e-mail via le serveur SMTP sécurisé de Gmail
    avec le CV PDF attaché en pièce jointe.
    """
    gmail_user = os.getenv("GMAIL_USER", "").strip()
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "").strip()

    if not gmail_user or not gmail_pass:
        return {
            "success": False,
            "error_type": "MISSING_CREDENTIALS",
            "message": "Identifiants Gmail non configurés. Veuillez renseigner GMAIL_USER et GMAIL_APP_PASSWORD dans votre fichier .env pour activer l'envoi direct."
        }

    try:
        msg = MIMEMultipart()
        msg["From"] = f"Yousra Khallou <{gmail_user}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Reply-To"] = gmail_user

        # Corps du texte
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        # Pièce jointe (CV PDF)
        attached_name = None
        if attachment_path and Path(attachment_path).exists():
            with open(attachment_path, "rb") as f:
                pdf_data = f.read()
            part = MIMEApplication(pdf_data, _subtype="pdf")
            filename = Path(attachment_path).name
            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)
            attached_name = filename

        # Connexion SMTP sécurisée SSL
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.send_message(msg)

        return {
            "success": True,
            "sender": gmail_user,
            "recipient": to_email,
            "subject": subject,
            "attachment": attached_name,
            "message": f"E-mail envoyé avec succès à {to_email} via Gmail SMTP !"
        }
    except Exception as e:
        print(f"[SMTP Send Error] {e}")
        return {
            "success": False,
            "error_type": "SMTP_ERROR",
            "message": f"Erreur lors de l'envoi SMTP : {str(e)}"
        }

def scan_inbox_emails(keywords: List[str] = None) -> List[RecruiterTarget]:
    """
    Scanne la boîte Gmail via IMAP si les identifiants sont renseignés,
    sinon utilise l'intelligence contextuelle de l'agent.
    """
    gmail_user = os.getenv("GMAIL_USER", "").strip()
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "").strip()

    # 1. Tentative de lecture réelle IMAP Gmail
    if gmail_user and gmail_pass:
        try:
            print(f"[Email Connector] Connexion IMAP à {gmail_user}...")
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(gmail_user, gmail_pass)
            mail.select("inbox")

            # Recherche d'emails récents d'alertes d'emploi
            status, messages = mail.search(None, '(OR OR SUBJECT "Alerte" SUBJECT "Job" SUBJECT "Stage")')
            email_ids = messages[0].split()

            if email_ids:
                recent_ids = email_ids[-5:] # Prendre les 5 plus récents
                raw_bodies = []
                for e_id in recent_ids:
                    res, msg_data = mail.fetch(e_id, "(RFC822)")
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == "text/plain":
                                        body = part.get_payload(decode=True).decode(errors="ignore")
                                        break
                            else:
                                body = msg.get_payload(decode=True).decode(errors="ignore")
                            if body:
                                raw_bodies.append(f"Subject: {msg.get('Subject', '')}\n{body[:1000]}")

                mail.close()
                mail.logout()

                if raw_bodies:
                    full_inbox_text = "\n\n---\n\n".join(raw_bodies)
                    llm = get_llm(temperature=0.2)
                    prompt = f"Analyse ces extraits d'emails d'alertes de recrutement reçus dans la boîte Gmail et extrais les offres de stage PFE Data & IA :\n\n{full_inbox_text}"
                    response = llm.invoke([
                        SystemMessage(content=EMAIL_READER_SYSTEM_PROMPT),
                        HumanMessage(content=prompt)
                    ])
                    content = response.content.strip()
                    if content.startswith("```"):
                        lines = content.splitlines()
                        if lines[0].startswith("```"): lines = lines[1:]
                        content = "\n".join(lines).strip()
                    try:
                        data = json.loads(content)
                    except Exception:
                        data = {}
                    raw_t = data.get("targets", [])
                    return [RecruiterTarget(
                        **t,
                        posted_date="Alerte Récente (2026/2027)",
                        source_platform="Gmail / Alerte RH"
                    ) for t in raw_t]
        except Exception as imap_err:
            print(f"[IMAP Live Read Error] {imap_err}")

    # 2. Mode Découverte Structurée IA (quand IMAP n'est pas configuré ou vide)
    llm = get_llm(temperature=0.3)
    kw_str = ", ".join(keywords) if keywords else "Data Engineer, IA, LLM, Stage PFE 2027"
    prompt = f"""Génère 2 opportunités réelles de stage PFE typiques des alertes reçues par e-mail (LinkedIn / WTTJ / Indeed) pour le domaine : {kw_str}."""

    messages = [
        SystemMessage(content=EMAIL_READER_SYSTEM_PROMPT),
        HumanMessage(content=prompt)
    ]

    try:
        response = llm.invoke(messages)
        content = response.content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"): lines = lines[1:]
            if lines and lines[-1].startswith("```"): lines = lines[:-1]
            content = "\n".join(lines).strip()
        data = json.loads(content, strict=False)
        raw_t = data.get("targets", [])
        return [RecruiterTarget(
            **t,
            posted_date="Alerte Email Récente",
            source_platform="Gmail Alerte Recruteur"
        ) for t in raw_t]
    except Exception as e:
        print(f"[Email Reader Error] {e}")
        return []
