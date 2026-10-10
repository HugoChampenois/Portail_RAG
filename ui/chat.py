"""Page « Assistant IA » : chat RAG avec sources citées."""
from __future__ import annotations

import streamlit as st

from core import index as idx
from core import llm
from core import rag
from ui import navigation as nav


def _render_sources(docs) -> None:
    if not docs:
        return
    st.markdown("#### Sources")
    for i, d in enumerate(docs, start=1):
        titre = d.get("titre") or d.get("doc_id") or ""
        if st.button(f"[{i}] {titre[:90]}", key=f"src_{i}_{d.get('doc_id')}"):
            resolved = idx.resolve_doc_id(d.get("doc_id", ""))
            if resolved:
                nav.navigate(
                    nav.make_doc(resolved["path"], anchor=resolved["anchor"], label=titre)
                )
                st.rerun()


def render() -> None:
    st.title("Assistant IA")

    if not llm.is_configured():
        st.info(
            "Aucun LLM n'est configuré. Rendez-vous dans la page « Paramètres IA » "
            "pour renseigner un fournisseur, un modèle et éventuellement une clé API."
        )
        return

    client = llm.get_client()
    if client is None:
        st.info("Configuration incomplète.")
        return

    st.session_state.setdefault("chat_history", [])

    # Effacer la conversation
    c1, c2 = st.columns([5, 1])
    with c2:
        if st.button("🗑 Effacer", disabled=not st.session_state.chat_history):
            st.session_state.chat_history = []
            st.rerun()

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prompt = st.chat_input("Posez une question juridique…")
    if prompt:
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        docs = rag.retrieve(prompt)
        prior = st.session_state.chat_history[:-1]
        messages = rag.build_messages(prompt, prior, docs)

        with st.chat_message("assistant"):
            try:
                reply = st.write_stream(client.stream(messages))
            except llm.LLMError as exc:
                reply = f"Erreur LLM : {exc}"
                st.error(reply)

        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        _render_sources(docs)
