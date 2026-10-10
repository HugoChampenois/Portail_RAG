"""Lecture d'un document : rendu Markdown + wikilinks + favori + backlinks + résumé."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import streamlit as st

from core import favorites
from core import highlight
from core import index as idx
from core import llm
from core import markdown as md
from core import rag
from core import wikilinks
from ui import navigation as nav

_BLOCK_SPLIT = re.compile(r"\n{2,}")
_MAX_LINKS_PER_BLOCK = 30
_MAX_ARTICLES = 200
# Fichiers consolidés (avec sommaire) : lecteur à ancre plutôt que rendu complet.
_CONSOLIDATED_TYPES = {"code", "jurisprudence", "lois_reglements", "procedure"}


def _labelize(text: str) -> str:
    text = wikilinks.strip_anchor_marks(text)
    for link in wikilinks.find_wikilinks(text):
        text = text.replace(link.raw, f"**{link.label}**")
    return text


def _render_links(links: List[wikilinks.Wikilink], current_path: str, key_base: str) -> None:
    resolved: List[tuple] = []
    for link in links:
        target = wikilinks.resolve(link, current_path)
        if target is not None:
            resolved.append((link, target))
    if not resolved:
        return

    resolved = resolved[:_MAX_LINKS_PER_BLOCK]
    cols = st.columns(len(resolved))
    for i, (link, target) in enumerate(resolved):
        with cols[i]:
            if st.button(f"🔗 {link.label}", key=f"{key_base}_{i}_{link.anchor or link.target}"):
                nav.navigate(
                    nav.make_doc(target["path"], anchor=target.get("anchor"), label=link.label)
                )
                st.rerun()


def _render_body(body: str, current_path: str, terms: List[str]) -> None:
    blocks = _BLOCK_SPLIT.split(body)
    counter = 0
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        links = wikilinks.find_wikilinks(block)
        text = _labelize(block)
        if terms:
            st.markdown(highlight.highlight(text, terms), unsafe_allow_html=True)
        else:
            st.markdown(text)
        if links:
            _render_links(links, current_path, f"lk_{current_path}_{counter}")
            counter += 1


def _meta_line(meta: Dict[str, Any]) -> str:
    parts = []
    for key in ("source", "statut", "date", "num", "annee", "matiere", "juridiction", "domaine", "pourvoi"):
        val = meta.get(key)
        if val:
            parts.append(f"{key}: {val}")
    if meta.get("date_fin"):
        parts.append(f"fin: {meta['date_fin']}")
    return " · ".join(parts)


def _slug_from_path(path: str) -> str:
    return path.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _toc_entries(path: str, data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Sommaire d'un fichier consolidé : liste de {anchor, label, statut}."""
    mtype = data["meta"].get("type")
    if mtype == "code":
        slug = data["meta"].get("id") or _slug_from_path(path)
        return [
            {"anchor": a["anchor"], "label": f"Article {a['num_disp']}", "statut": a["statut"] or ""}
            for a in idx.list_code_articles(slug)
        ]
    return [
        {"anchor": e["anchor"], "label": e["label"], "statut": ""}
        for e in md.parse_toc(data["body"])
    ]


def _render_toc_reader(path: str, entries: List[Dict[str, str]], key: str) -> None:
    if not entries:
        st.info("Sommaire introuvable pour ce fichier.")
        return

    st.caption(f"{len(entries)} entrées")
    q = st.text_input("Filtrer", key=f"filter_{key}", placeholder="filtrer par libellé…")
    if q.strip():
        shown = [e for e in entries if q.strip().lower() in (e["label"] or "").lower()]
    else:
        shown = entries

    shown = shown[:_MAX_ARTICLES]
    for e in shown:
        statut = e.get("statut") or ""
        label = e["label"] + (f" ({statut})" if statut else "")
        if st.button(label, key=f"toc_{key}_{e['anchor']}"):
            nav.navigate(nav.make_doc(path, anchor=e["anchor"], label=e["label"]))
            st.rerun()

    if len(shown) >= _MAX_ARTICLES:
        st.caption(f"Affichage limité à {_MAX_ARTICLES} entrées — affinez le filtre.")


def _render_backlinks(path: str, anchor: Optional[str]) -> None:
    backlinks = idx.get_backlinks(path, anchor or "")
    if not backlinks:
        return
    st.markdown("#### Référencé par")
    for b in backlinks:
        label = b["source_titre"] or b["source_id"]
        if st.button(f"↳ {label[:80]}", key=f"bl_{b['source_id']}_{anchor}"):
            resolved = idx.resolve_doc_id(b["source_id"])
            if resolved:
                nav.navigate(
                    nav.make_doc(resolved["path"], anchor=resolved["anchor"], label=label)
                )
                st.rerun()


def _render_summary(path: str, anchor: Optional[str], body: str) -> None:
    if not llm.is_configured():
        st.info("Configurez un LLM dans la page « Paramètres IA » pour résumer un document.")
        return
    if st.button("🤖 Résumer ce document", key=f"sum_{path}_{anchor or ''}"):
        client = llm.get_client()
        if client is None:
            st.info("LLM non configuré.")
            return
        try:
            with st.spinner("Résumé en cours…"):
                stream = client.stream(rag.summarize_messages(body))
                st.write_stream(stream)
        except llm.LLMError as exc:
            st.error(f"Erreur LLM : {exc}")


def render_document(doc: Dict[str, Any]) -> None:
    path = doc["path"]
    anchor = doc.get("anchor")

    try:
        data = md.load(path, anchor)
    except FileNotFoundError:
        st.error(f"Fichier introuvable : `{path}`")
        if st.button("← Retour"):
            nav.go_back()
            st.rerun()
        return
    except Exception as exc:  # noqa: BLE001
        st.error(f"Erreur de lecture : {exc}")
        return

    mtype = data["meta"].get("type")
    is_consolidated = mtype in _CONSOLIDATED_TYPES

    # En-tête : titre + favori
    hcol1, hcol2 = st.columns([0.9, 0.1])
    with hcol1:
        st.markdown(f"## {data['title']}")
    with hcol2:
        fav = favorites.is_favorite(path, anchor or "")
        if st.button("★" if fav else "☆", key=f"fav_{path}_{anchor or ''}",
                     help="Ajouter/retirer des favoris"):
            favorites.toggle(path, anchor or "", data["title"])
            st.rerun()

    # Fichier consolidé ouvert sans ancre : lecteur de sommaire filtrable.
    if is_consolidated and not anchor:
        meta_line = _meta_line(data["meta"])
        if meta_line:
            st.caption(meta_line)
        st.divider()
        _render_toc_reader(path, _toc_entries(path, data), _slug_from_path(path))
        st.divider()
        st.caption(f"Source : `{path}`")
        return

    if data["is_extract"]:
        st.caption(f"Extrait de `{path}`")
        if is_consolidated:
            if st.button("📖 Afficher le fichier complet", key=f"full_{path}"):
                nav.navigate(nav.make_doc(path, anchor=None, label=data["title"]))
                st.rerun()

    meta_line = _meta_line(data["meta"])
    if meta_line:
        st.caption(meta_line)

    tags = data["meta"].get("tags")
    if tags:
        st.caption("Tags : " + " · ".join(tags[:16]))

    st.divider()

    terms = highlight.query_terms(st.session_state.get("search_query", ""))
    _render_body(data["body"], path, terms)

    st.divider()

    _render_summary(path, anchor, data["body"])
    _render_backlinks(path, anchor)

    st.caption(f"Source : `{path}`")
