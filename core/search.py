"""Recherche sémantique directe dans Qdrant.

Le portail embarque la requête (Ollama local) puis interroge Qdrant. Les
résultats sont dédupliqués par `doc_id` (un document est découpé en plusieurs
chunks ; on ne garde que le chunk le plus pertinent par document).
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny

import config
from core import index as idx
from core.embedder import embed_one


class SearchError(RuntimeError):
    """Qdrant est indisponible ou la requête a échoué."""


def get_client() -> QdrantClient:
    return QdrantClient(url=config.QDRANT_URL, timeout=120)


def _dedup_by_doc(points: List[Any]) -> List[Dict[str, Any]]:
    """Garde le meilleur chunk (score max) par `doc_id`, en ordre décroissant."""
    best: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for point in points:
        payload = point.payload or {}
        doc_id = payload.get("doc_id") or str(point.id)
        score = float(getattr(point, "score", None) or 0.0)
        if doc_id not in best or score > best[doc_id]["score"]:
            if doc_id not in best:
                order.append(doc_id)
            best[doc_id] = {
                "score": score,
                "doc_id": doc_id,
                "source": payload.get("source", ""),
                "statut": payload.get("statut", ""),
                "date": payload.get("date", ""),
                "date_fin": payload.get("date_fin", ""),
                "num": payload.get("num", ""),
                "titre": payload.get("titre", ""),
                "tags": payload.get("tags", []),
                "obsidian_path": payload.get("obsidian_path", ""),
                "chunk_index": payload.get("chunk_index"),
                "chunk_count": payload.get("chunk_count"),
                "extrait": payload.get("chunk_text", ""),
            }
    return [best[doc_id] for doc_id in order]


def _build_filter(tag_groups: List[List[str]]) -> Optional[Filter]:
    """Construit le filtre Qdrant sur le champ payload `tags`.

    `tag_groups` est une liste de groupes de tags. Au sein d'un groupe, les
    tags sont combinés en OU (MatchAny) ; entre groupes, en ET (must).
    """
    must = []
    for group in (tag_groups or []):
        group = [t for t in group if t]
        if group:
            must.append(FieldCondition(key="tags", match=MatchAny(any=group)))
    if not must:
        return None
    return Filter(must=must)


def _filter_by_type(results: List[Dict[str, Any]], types: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Post-filtre les résultats par type de document (via l'index)."""
    if not types:
        return results
    type_map = idx.get_types([r.get("doc_id") for r in results])
    return [r for r in results if type_map.get(r.get("doc_id")) in types]


def _point_id(doc_id: str, chunk_index: int = 0) -> str:
    """UUID déterministe du point Qdrant (identique à rag_droit/ingest.py)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}::{chunk_index}"))


def _record_to_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "score": 0.0,
        "doc_id": payload.get("doc_id", ""),
        "source": payload.get("source", ""),
        "statut": payload.get("statut", ""),
        "date": payload.get("date", ""),
        "date_fin": payload.get("date_fin", ""),
        "num": payload.get("num", ""),
        "titre": payload.get("titre", ""),
        "tags": payload.get("tags", []),
        "chunk_index": payload.get("chunk_index"),
        "chunk_count": payload.get("chunk_count"),
        "extrait": payload.get("chunk_text", ""),
    }


def search_by_type(types: List[str], limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Recherche par type de document uniquement (via l'index + Qdrant retrieve)."""
    limit = max(1, min(limit or config.SEARCH_LIMIT, 100))
    doc_ids = idx.get_doc_ids_by_type(types, limit * 4)
    if not doc_ids:
        return []

    try:
        client = get_client()
        records = client.retrieve(
            collection_name=config.COLLECTION,
            ids=[_point_id(d) for d in doc_ids],
            with_payload=True,
            with_vectors=False,
        )
    except Exception as exc:
        raise SearchError(f"Qdrant injoignable : {exc}") from exc

    results = [_record_to_result(r.payload) for r in records if r.payload]
    results.sort(key=lambda r: r.get("date") or "", reverse=True)
    return results[:limit]


def search_by_tags(
    tag_groups: List[List[str]],
    limit: Optional[int] = None,
    types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Recherche par tags uniquement (sans requête) : scroll filtré + déduplication.

    Les points sont triés par date décroissante (ordre déterministe faute de
    score de similarité).
    """
    limit = max(1, min(limit or config.SEARCH_LIMIT, 100))
    fetch = limit * config.SEARCH_FETCH_MULTIPLIER
    if types:
        fetch = max(fetch, 300)
    filt = _build_filter(tag_groups)
    if filt is None and not types:
        return []

    try:
        client = get_client()
        if filt is not None:
            points, _ = client.scroll(
                collection_name=config.COLLECTION,
                scroll_filter=filt,
                limit=fetch,
                with_payload=True,
                with_vectors=False,
            )
        else:
            points, _ = client.scroll(
                collection_name=config.COLLECTION,
                limit=fetch,
                with_payload=True,
                with_vectors=False,
            )
    except Exception as exc:
        raise SearchError(f"Qdrant injoignable : {exc}") from exc

    results = _dedup_by_doc(points)
    results = _filter_by_type(results, types)
    results.sort(key=lambda r: r.get("date") or "", reverse=True)
    return results[:limit]


def search(
    query: str,
    limit: Optional[int] = None,
    tag_groups: Optional[List[List[str]]] = None,
    types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Recherche top-k documents, dédupliqués par document, filtrage par tags/type.

    Si la requête est vide mais que des tags ou un type sont fournis, effectue
    une recherche par tags uniquement (parcours filtré).
    """
    query = (query or "").strip()
    if not query:
        has_tags = bool(tag_groups and any(g for g in tag_groups))
        if types and not has_tags:
            return search_by_type(types, limit)
        if has_tags or types:
            return search_by_tags(tag_groups, limit, types)
        return []

    limit = max(1, min(limit or config.SEARCH_LIMIT, 100))
    fetch = limit * config.SEARCH_FETCH_MULTIPLIER
    if types:
        fetch = max(fetch, 300)

    try:
        vector = embed_one(query)
    except Exception as exc:
        raise SearchError(f"Embedding impossible : {exc}") from exc

    try:
        client = get_client()
        resp = client.query_points(
            collection_name=config.COLLECTION,
            query=vector,
            limit=fetch,
            with_payload=True,
            query_filter=_build_filter(tag_groups),
        )
    except Exception as exc:
        raise SearchError(f"Qdrant injoignable : {exc}") from exc

    results = _dedup_by_doc(resp.points)
    results = _filter_by_type(results, types)
    return results[:limit]
