"""Page « Paramètres IA » : configuration du LLM (OpenAI-compatible)."""
from __future__ import annotations

import streamlit as st

import config
from core import llm


def render() -> None:
    st.title("Paramètres IA")
    st.caption(
        "Configurez le modèle de langage utilisé par l'assistant. Tout fournisseur "
        "exposant une API compatible OpenAI (`/v1/chat/completions`) fonctionne : "
        "OpenAI, DeepSeek, Mistral, Groq, vLLM ou Ollama."
    )

    cfg = llm.load_config()

    providers = list(config.LLM_PRESETS.keys())
    current = cfg.get("provider", "")
    index = providers.index(current) if current in providers else 0

    provider = st.selectbox("Fournisseur", providers, index=index)

    preset = config.LLM_PRESETS[provider]
    base_url = st.text_input("URL de base", value=cfg.get("base_url") or preset["base_url"])
    model = st.text_input("Modèle", value=cfg.get("model") or preset["model"])

    api_key = ""
    if preset.get("needs_key", True):
        api_key = st.text_input("Clé API", type="password", value=cfg.get("api_key", ""))

    if st.button("Enregistrer", type="primary"):
        llm.save_config(
            {
                "provider": provider,
                "base_url": base_url.strip(),
                "model": model.strip(),
                "api_key": api_key.strip(),
            }
        )
        st.success("Configuration enregistrée.")
        st.rerun()

    st.divider()
    if llm.is_configured():
        st.success(f"Configuré : `{cfg.get('model')}` sur `{cfg.get('base_url')}`")
    else:
        st.info("Aucun LLM configuré pour l'instant.")
