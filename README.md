# 🎯 PFE AI Job Hunter (Multi-Agent LangGraph)

Agent IA autonome conçu pour automatiser et ultra-personnaliser la recherche de stage de fin d'études (PFE) d'élèves ingénieurs.

---

## 🌟 Fonctionnalités

1. **Extraction Intelligente de Cibles (Post LinkedIn, alertes, emails)** :
   - Extrait les emails RH, noms d'entreprises, postes, localisations et technologies depuis du texte brut ou des posts LinkedIn.
2. **Matching Sémantique & Scoring IA** :
   - Compare les exigences de l'offre avec **votre CV / profil**.
   - Calcule un score de pertinence (0-100%).
   - Identifie le projet le plus pertinent de votre portfolio à mettre en avant.
3. **Rédaction Ultra-Personnalisée (Zéro Clichés)** :
   - Rédige un email direct, technique et percutant basé sur la méthode *Accroche -> Preuve de valeur -> Call to action*.
4. **Export & Sauvegarde** :
   - Sauvegarde les candidatures prêtes à l'envoi au format JSON / Markdown.

---

## 🛠️ Stack Technique

* **Framework Agent** : [LangGraph](https://github.com/langchain-ai/langgraph) / LangChain
* **LLM Engine** : [NVIDIA Build NIM](https://build.nvidia.com/) (Llama 3.3 70B / DeepSeek / Mistral)
* **Typage & Validation** : Pydantic V2
* **Interface CLI** : Rich Console

---

## 🚀 Démarrage Rapide

### 1. Installation des dépendances

```bash
pip install -r pfe_agent/requirements.txt
```

### 2. Configuration de la clé NVIDIA API

Créez le fichier `pfe_agent/.env` :
```env
NVIDIA_API_KEY=nvapi-votre-cle-ici
NVIDIA_MODEL=meta/llama-3.3-70b-instruct
```

### 3. Personnalisez votre profil

Éditez le fichier [`pfe_agent/profile_data.json`](./profile_data.json) avec votre nom, vos compétences et vos vrais projets réalisés.

### 4. Lancez l'agent

```bash
python -m pfe_agent.main
```
