"""Écran d'accueil : recherche sémantique + filtres par tags + résultats en cartes."""
from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from core import highlight
from core import index as idx
from core import search as search_mod
from core.canon import MATIERE_FOLDER, RACINE_FOLDER
from ui import navigation as nav

_BADGE_STYLE = (
    "display:inline-block;background:#1f2a44;color:#cfd8ea;border-radius:6px;"
    "padding:2px 8px;margin-right:6px;font-size:0.75rem;"
)
_CATEGORY_LABELS = {
    "racine": "Racine",
    "juridiction": "Juridiction",
    "matiere": "Matière",
    "statut": "Statut",
    "autres": "Autres",
}
_CATEGORY_ORDER = ["racine", "juridiction", "matiere", "statut", "autres"]
_TYPE_OPTIONS = {
    "code": "Code",
    "lois_reglements": "Lois et règlements",
    "jurisprudence": "Jurisprudence (inédite)",
    "procedure": "Jurisprudence (publiée)",
}
_PAGE_SIZE = 10
_FETCH_LIMIT = 50
_MAX_TAG_OPTIONS = 40


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _badges_html(source: str, statut: str, date: str, num: str, dtype: str = "") -> str:
    parts = []
    if dtype:
        label = _TYPE_OPTIONS.get(dtype, dtype)
        parts.append(f"<span style='{_BADGE_STYLE}background:#2a3b5c'>{_esc(label)}</span>")
    if source:
        parts.append(f"<span style='{_BADGE_STYLE}'>{_esc(source)}</span>")
    if statut:
        parts.append(f"<span style='{_BADGE_STYLE}'>{_esc(statut)}</span>")
    if date:
        parts.append(f"<span style='{_BADGE_STYLE}'>{_esc(date)}</span>")
    if num:
        parts.append(f"<span style='{_BADGE_STYLE}'>art. {_esc(num)}</span>")
    return "".join(parts)


def _load_tag_counts() -> Dict[str, List[Dict[str, str]]]:
    """Tag counts groupés par catégorie."""
    grouped: Dict[str, List[Dict[str, str]]] = {c: [] for c in _CATEGORY_ORDER}
    for item in idx.get_tag_counts():
        cat = item["category"] if item["category"] in grouped else "autres"
        grouped[cat].append(item)
    return grouped


def _tag_label(tag: str, category: str) -> str:
    if category == "matiere":
        return MATIERE_FOLDER.get(tag, tag).replace("_", " ")
    if category == "racine":
        return RACINE_FOLDER.get(tag, tag).replace("_", " ")
    return tag


def _render_tag_filters() -> None:
    """Rend les filtres par tags (multi-sélection groupée avec compteurs)."""
    grouped = _load_tag_counts()
    for cat in _CATEGORY_ORDER:
        items = grouped[cat][:_MAX_TAG_OPTIONS]
        if not items:
            continue
        counts = {i["tag"]: i["count"] for i in items}
        options = [i["tag"] for i in items]
        with st.expander(f"{_CATEGORY_LABELS[cat]} ({len(grouped[cat])} tags)"):
            selected = st.multiselect(
                "Tags",
                options=options,
                key=f"tag_filter_{cat}",
                format_func=lambda t, c=counts, cat2=cat: f"{_tag_label(t, cat2)} ({c.get(t, 0)})",
                label_visibility="collapsed",
            )
            st.session_state.search_tags[cat] = selected


def _collect_tag_groups() -> List[List[str]]:
    groups = []
    for cat in _CATEGORY_ORDER:
        sel = st.session_state.search_tags.get(cat) or []
        if sel:
            groups.append(list(sel))
    return groups


def _collect_types() -> List[str]:
    return list(st.session_state.get("search_types") or [])


def _render_card(result: Dict[str, Any], position: int, terms: List[str]) -> None:
    titre = result.get("titre") or result.get("doc_id") or "Sans titre"
    extrait = (result.get("extrait") or "").strip()
    tags = result.get("tags") or []
    doc_id = result.get("doc_id") or ""

    with st.container(border=True):
        resolved = idx.resolve_doc_id(doc_id)
        st.markdown(
            f"<strong>{highlight.highlight(titre, terms)}</strong>",
            unsafe_allow_html=True,
        )
        st.markdown(
            _badges_html(
                result.get("source"),
                result.get("statut"),
                result.get("date"),
                result.get("num"),
                dtype=(resolved or {}).get("type") or "",
            ),
            unsafe_allow_html=True,
        )
        if extrait:
            st.markdown(
                f"<div style='color:#9aa7bd;font-size:0.85rem'>"
                f"{highlight.highlight(extrait[:400], terms)}</div>",
                unsafe_allow_html=True,
            )
        if tags:
            st.caption(" · ".join(tags[:8]))

        if resolved is None:
            st.warning("Document non localisé dans le Vault (index à régénérer ?).")
            return
        if st.button("Ouvrir le document", key=f"open_{position}_{doc_id}"):
            nav.navigate(
                nav.make_doc(resolved["path"], anchor=resolved["anchor"], label=titre)
            )
            st.rerun()


def _run_search(query: str) -> None:
    st.session_state.search_query = query
    st.session_state.search_ran = True
    st.session_state.search_page_idx = 0
    try:
        st.session_state.search_results = search_mod.search(
            query,
            limit=_FETCH_LIMIT,
            tag_groups=_collect_tag_groups(),
            types=_collect_types(),
        )
        st.session_state.search_error = None
    except Exception as exc:  # noqa: BLE001
        st.session_state.search_results = []
        st.session_state.search_error = str(exc)


def _render_autocomplete(query: str) -> bool:
    """Affiche les suggestions ; retourne True si une suggestion a été choisie."""
    if len(query) < 2 or st.session_state.search_ran and st.session_state.search_query == query:
        return False
    suggestions = idx.suggest_titles(query, limit=8)
    if not suggestions:
        return False
    st.caption("Suggestions :")
    cols = st.columns(len(suggestions))
    chosen = False
    for i, s in enumerate(suggestions):
        with cols[i]:
            if st.button(s["titre"][:60], key=f"sug_{i}_{s['path']}"):
                st.session_state.search_q = s["titre"]
                chosen = True
    return chosen


def render() -> None:
    st.title("Portail juridique")
    st.caption(
        "Recherche sémantique (Qdrant) et navigation hypertexte dans le Vault Obsidian."
    )

    query = st.text_input(
        "Requête",
        key="search_q",
        placeholder="ex. article 1382 code civil, harcèlement moral, bail commercial…",
    )

    with st.expander("Type de document"):
        selected_types = st.multiselect(
            "Types",
            options=list(_TYPE_OPTIONS.keys()),
            key="type_filter",
            format_func=lambda t: _TYPE_OPTIONS[t],
            label_visibility="collapsed",
        )
        st.session_state.search_types = selected_types

    with st.expander("Filtres par tags"):
        st.caption("Vous pouvez rechercher par tags seuls, sans mots-clés.")
        _render_tag_filters()

    col1, col2 = st.columns([1, 4])
    with col1:
        search_clicked = st.button("Rechercher", type="primary", use_container_width=True)

    if _render_autocomplete(query):
        _run_search(st.session_state.search_q)
        st.rerun()

    if search_clicked:
        _run_search(query)

    if not st.session_state.search_ran:
        st.info("Saisissez une requête et/ou des tags, puis cliquez sur « Rechercher ».")
        return

    if st.session_state.search_error:
        st.error(f"Recherche impossible : {st.session_state.search_error}")
        return

    results: List[Dict[str, Any]] = st.session_state.search_results
    if not results:
        st.info("Aucun résultat.")
        return

    terms = highlight.query_terms(st.session_state.search_query)
    total = len(results)
    page_idx = st.session_state.search_page_idx
    start = page_idx * _PAGE_SIZE
    end = start + _PAGE_SIZE
    page = results[start:end]

    st.subheader(f"Résultats ({total})")
    if total > _PAGE_SIZE:
        n_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
        p1, p2, p3 = st.columns([1, 1, 3])
        with p1:
            if st.button("← Précédent", disabled=page_idx == 0):
                st.session_state.search_page_idx -= 1
                st.rerun()
        with p2:
            if st.button("Suivant →", disabled=page_idx >= n_pages - 1):
                st.session_state.search_page_idx += 1
                st.rerun()
        with p3:
            st.caption(f"Page {page_idx + 1}/{n_pages}")

    for i, res in enumerate(page):
        _render_card(res, start + i, terms)
