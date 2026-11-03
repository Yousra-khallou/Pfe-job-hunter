import os
import sys
import time
import logging
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

logger = logging.getLogger("pfe_agent.config")

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

current_dir = Path(__file__).parent
env_path = current_dir / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

# Google Gemini Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
GEMINI_DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# NVIDIA NIM Configuration (Fallback)
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_DEFAULT_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct")

# Choix du provider : si GEMINI_API_KEY est présent, on utilise Gemini par défaut
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini" if GEMINI_API_KEY else "nvidia").lower()

def get_llm(model_name: str = None, temperature: float = 0.2) -> ChatOpenAI:
    provider = os.getenv("LLM_PROVIDER", "gemini" if GEMINI_API_KEY else "nvidia").lower()
    
    # 1. Utilisation prioritaire de Google Gemini
    if provider == "gemini" and GEMINI_API_KEY:
        model = model_name or os.getenv("GEMINI_MODEL", GEMINI_DEFAULT_MODEL)
        return ChatOpenAI(
            model=model,
            api_key=GEMINI_API_KEY,
            base_url=GEMINI_BASE_URL,
            temperature=temperature,
            max_retries=5,
            timeout=45.0,
        )
    
    # 2. Utilisation de NVIDIA NIM
    api_key = NVIDIA_API_KEY or os.getenv("NVIDIA_API_KEY", "")
    if not api_key or api_key.startswith("nvapi-your-key"):
        raise ValueError(
            "Aucune clé API LLM valide trouvée ! Veuillez renseigner GEMINI_API_KEY ou NVIDIA_API_KEY dans votre fichier .env."
        )

    model = model_name or os.getenv("NVIDIA_MODEL", NVIDIA_DEFAULT_MODEL)
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=NVIDIA_BASE_URL,
        temperature=temperature,
        max_retries=3,
        timeout=60.0,
    )


def invoke_llm(llm, messages, max_retries: int = 3, backoff: float = 2.0):
    """Appelle llm.invoke() avec retry automatique si la réponse est vide.
    
    Résout l'erreur : 'model output must contain either output text or tool calls'.
    Cela arrive quand le modèle retourne une réponse vide (filtre de sécurité,
    context trop long, ou débit API dépassé).
    """
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = llm.invoke(messages)
            content = getattr(response, "content", "") or ""
            if content.strip():
                return response
            # Réponse vide : on réessaie
            logger.warning(f"[LLM] Réponse vide (tentative {attempt}/{max_retries}), retry dans {backoff}s...")
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            # Erreur de réponse vide connue → on réessaie
            if "model output" in err_str or "empty" in err_str or "output text" in err_str:
                logger.warning(f"[LLM] Erreur réponse vide (tentative {attempt}/{max_retries}): {e}")
            else:
                # Autre erreur → on la propage immédiatement
                raise
        if attempt < max_retries:
            time.sleep(backoff * attempt)
    
    # Tous les essais échoués : on lève la dernière erreur ou on retourne une réponse vide simulée
    if last_error:
        raise last_error
    # Simuler une réponse vide pour que l'appelant puisse gérer son fallback
    from langchain_core.messages import AIMessage
    logger.error("[LLM] Toutes les tentatives ont échoué, retour d'une réponse vide.")
    return AIMessage(content="{}")
