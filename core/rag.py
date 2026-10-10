"""Chaîne RAG : récupération de contexte + prompts pour l'assistant juridique."""
from __future__ import annotations

from typing import Any, Dict, List

import config
from core import search as search_mod

SYSTEM_PROMPT = (
    "Tu es un assistant juridique spécialisé en droit français. Tu réponds "
    "uniquement à partir des extraits fournis ci-dessous (issus d'une base de "
    "documents juridiques DILA). Réponds en français, de façon précise et "
    "structurée. Cite tes sources entre crochets, par exemple [1] ou [1][3]. "
    "Si les extraits ne permettent pas de répondre, dis-le clairement au lieu "
    "d'inventer."
)


def retrieve(query: str, top_k: int = None) -> List[Dict[str, Any]]:
    """Récupère les documents les plus pertinents (sans filtrage par tags)."""
    top_k = top_k or config.RAG_TOP_K
    try:
        return search_mod.search(query, limit=top_k)
    except search_mod.SearchError:
        return []


def build_context(docs: List[Dict[str, Any]]) -> str:
    """Assemble un contexte textuel borné à partir des documents récupérés."""
    budget = config.RAG_CONTEXT_CHARS
    parts: List[str] = []
    used = 0
    for i, doc in enumerate(docs, start=1):
        titre = doc.get("titre") or doc.get("doc_id") or ""
        source = doc.get("source") or ""
        extrait = (doc.get("extrait") or "").strip()
        block = f"[{i}] {titre} ({source})\n{extrait}\n"
        if used + len(block) > budget and parts:
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts)


def build_messages(
    query: str,
    history: List[Dict[str, str]],
    docs: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Construit la liste de messages pour l'appel LLM."""
    context = build_context(docs)
    user = (
        f"Question : {query}\n\n"
        f"Extraits de référence :\n{context if context else '(aucun extrait)'}\n\n"
        "Réponds en citant les sources [n]."
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user})
    return messages


def summarize_messages(text: str) -> List[Dict[str, str]]:
    """Prompt de résumé d'un document."""
    text = (text or "").strip()
    if len(text) > config.RAG_CONTEXT_CHARS:
        text = text[: config.RAG_CONTEXT_CHARS]
    system = (
        "Tu es un juriste. Résume le document juridique suivant de façon claire "
        "et neutre : point de droit en cause, décision ou disposition principale, "
        "et portée. Réponds en français, en quelques paragraphes."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Document :\n{text}"},
    ]
