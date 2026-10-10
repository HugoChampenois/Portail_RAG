"""Configuration du portail RAG (lecture seule sur le pipeline RAG Droit)."""
from __future__ import annotations

import os

# --- Stockage (lecture seule) ---
# Racine du pipeline RAG Droit (surchargeable via PORTAIL_RAG_BASE).
RAG_BASE = os.environ.get("PORTAIL_RAG_BASE", "/opt/rag")
VAULT_DIR = os.environ.get("PORTAIL_VAULT_DIR", f"{RAG_BASE}/Vault_Obsidian")

# --- Qdrant (recherche sémantique) ---
QDRANT_URL = os.environ.get("PORTAIL_QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("PORTAIL_COLLECTION", "rag_droit")

# --- Embedding (Ollama local, bge-m3) ---
OLLAMA_URL = os.environ.get("PORTAIL_OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("PORTAIL_EMBED_MODEL", "bge-m3")
EMBED_TIMEOUT = float(os.environ.get("PORTAIL_EMBED_TIMEOUT", "120"))

# --- Index SQLite (doc_id -> chemin réel dans le Vault consolidé) ---
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_DB = os.environ.get("PORTAIL_INDEX_DB", os.path.join(DATA_DIR, "data", "index.db"))

# --- Recherche ---
SEARCH_LIMIT = int(os.environ.get("PORTAIL_SEARCH_LIMIT", "10"))
# Nombre de points Qdrant demandés par requête (on sur-échantillonne car
# plusieurs chunks appartiennent au même document, qu'on déduplique ensuite).
SEARCH_FETCH_MULTIPLIER = 4

# --- Favoris (persistants) ---
FAVORITES_PATH = os.environ.get(
    "PORTAIL_FAVORITES_PATH", os.path.join(DATA_DIR, "data", "favorites.json")
)

# --- Assistant IA (LLM OpenAI-compatible, configurable à chaud) ---
LLM_CONFIG_PATH = os.environ.get(
    "PORTAIL_LLM_CONFIG_PATH", os.path.join(DATA_DIR, "data", "llm_config.json")
)
# Préréglages de fournisseurs proposés dans l'interface.
LLM_PRESETS = {
    "API externe (clé)": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "needs_key": True},
    "DeepSeek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat", "needs_key": True},
    "Mistral": {"base_url": "https://api.mistral.ai/v1", "model": "mistral-small-latest", "needs_key": True},
    "GPU distant (vLLM)": {"base_url": "http://localhost:8000/v1", "model": "bge-m3", "needs_key": True},
    "Ollama local": {"base_url": "http://localhost:11434/v1", "model": "qwen2.5:3b", "needs_key": False},
}
# Nombre de documents récupérés pour le contexte RAG.
RAG_TOP_K = int(os.environ.get("PORTAIL_RAG_TOP_K", "5"))
# Taille max (caractères) du contexte envoyé au LLM.
RAG_CONTEXT_CHARS = int(os.environ.get("PORTAIL_RAG_CONTEXT_CHARS", "12000"))
