"""Point d'entrée du portail RAG.

Lancement :
    venv/bin/streamlit run app.py --server.port 8501
"""
from __future__ import annotations

import streamlit as st

from ui import chat, document, favorites_view, home, settings
from ui import navigation as nav

st.set_page_config(page_title="Portail RAG", page_icon="⚖️", layout="wide")

nav.ensure_state()

_PAGE_LABELS = {
    "recherche": "🔎 Recherche",
    "favoris": "★ Favoris",
    "assistant": "🤖 Assistant IA",
    "parametres": "⚙️ Paramètres IA",
}

# --------------------------------------------------------------------------- #
# Barre latérale : navigation globale
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.title("⚖️ Portail RAG")
    st.caption("Base juridique — DILA")

    for page, label in _PAGE_LABELS.items():
        if st.button(label, use_container_width=True, key=f"nav_{page}"):
            nav.set_page(page)
            st.rerun()

    st.divider()

    if st.session_state.current_doc is not None:
        if st.button("← Retour", type="primary", use_container_width=True):
            nav.go_back()
            st.rerun()
        trail = nav.breadcrumb(st.session_state.current_doc)
        if trail:
            st.markdown("**Fil d'Ariane**")
            st.caption(" › ".join(trail[-6:]))

    st.caption("Qdrant : localhost:6333")
    st.caption("Collection : rag_droit")

# --------------------------------------------------------------------------- #
# Zone principale
# --------------------------------------------------------------------------- #
if st.session_state.current_doc is not None:
    document.render_document(st.session_state.current_doc)
else:
    page = st.session_state.page
    if page == "favoris":
        favorites_view.render()
    elif page == "assistant":
        chat.render()
    elif page == "parametres":
        settings.render()
    else:
        home.render()
