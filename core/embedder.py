"""Client d'embedding de requêtes via Ollama local (bge-m3).

Le modèle `bge-m3` est servi localement sur `localhost:11434` (CPU). Les
requêtes du portail (1-2 lignes) sont embarquées ici, sans dépendre du bulk
GPU distant utilisé par le pipeline d'ingestion.
"""
from __future__ import annotations

from typing import List

import httpx

import config


class EmbedError(RuntimeError):
    """Le backend d'embedding est indisponible ou a renvoyé une erreur."""


def _post(payload: dict) -> dict:
    try:
        with httpx.Client(timeout=config.EMBED_TIMEOUT) as client:
            resp = client.post(f"{config.OLLAMA_URL}/api/embed", json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise EmbedError(
            f"Ollama injoignable sur {config.OLLAMA_URL} : {exc}"
        ) from exc


def embed(texts: List[str]) -> List[List[float]]:
    """Retourne un vecteur par texte, dans le même ordre."""
    if not texts:
        return []
    data = _post({"model": config.EMBED_MODEL, "input": list(texts)})
    embeddings = list(data.get("embeddings", []))
    if len(embeddings) != len(texts):
        raise EmbedError(
            f"Ollama a renvoyé {len(embeddings)} vecteurs pour {len(texts)} textes"
        )
    return embeddings


def embed_one(text: str) -> List[float]:
    vectors = embed([text])
    if not vectors:
        raise EmbedError("Embedding vide renvoyé par Ollama")
    return vectors[0]
