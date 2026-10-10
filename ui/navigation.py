"""Gestion de la navigation (session_state) : pages, historique, retour.

État :
- `page`        : page de premier niveau (recherche | favoris | assistant | parametres)
- `current_doc` : {path, anchor, label} si un document est en lecture (sinon None)
- `history`     : pile des documents précédents (bouton Retour)
- `search_*`    : résultats de la dernière recherche (conservés)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

PAGES = ["recherche", "favoris", "assistant", "parametres"]


def make_doc(path: str, anchor: Optional[str] = None, label: str = "") -> Dict[str, Any]:
    return {"path": path, "anchor": anchor, "label": label}


def ensure_state() -> None:
    st.session_state.setdefault("page", "recherche")
    st.session_state.setdefault("current_doc", None)
    st.session_state.setdefault("history", [])
    st.session_state.setdefault("search_query", "")
    st.session_state.setdefault("search_results", [])
    st.session_state.setdefault("search_error", None)
    st.session_state.setdefault("search_ran", False)
    st.session_state.setdefault("search_tags", {})  # catégorie -> [tags]
    st.session_state.setdefault("search_types", [])
    st.session_state.setdefault("search_page_idx", 0)


def set_page(page: str) -> None:
    """Change de page de premier niveau (ferme le document en cours)."""
    st.session_state.page = page
    st.session_state.current_doc = None


def navigate(doc: Dict[str, Any]) -> None:
    """Ouvre un document en empilant le document courant dans l'historique."""
    current = st.session_state.current_doc
    if current is not None:
        st.session_state.history.append(current)
    st.session_state.current_doc = doc


def go_back() -> None:
    """Retour au document précédent, sinon à la page."""
    if st.session_state.history:
        st.session_state.current_doc = st.session_state.history.pop()
    else:
        st.session_state.current_doc = None


def breadcrumb(doc: Dict[str, Any]) -> List[str]:
    trail = [d["path"] for d in st.session_state.history]
    if doc:
        trail.append(doc["path"])
    return trail
