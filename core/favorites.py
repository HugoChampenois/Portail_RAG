"""Favoris persistants (fichier JSON local).

Un favori est identifié par sa clé `path#anchor` (chemin dans le Vault + ancre
éventuelle). Stocke titre, path, anchor et date d'ajout.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List

import config


def _key(path: str, anchor: str = "") -> str:
    return f"{path}#{anchor or ''}"


def _load() -> Dict[str, Dict[str, Any]]:
    if not os.path.exists(config.FAVORITES_PATH):
        return {}
    try:
        with open(config.FAVORITES_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(favs: Dict[str, Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(config.FAVORITES_PATH), exist_ok=True)
    tmp = config.FAVORITES_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(favs, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, config.FAVORITES_PATH)


def list_favorites() -> List[Dict[str, Any]]:
    items = list(_load().values())
    items.sort(key=lambda f: f.get("date", ""), reverse=True)
    return items


def is_favorite(path: str, anchor: str = "") -> bool:
    return _key(path, anchor) in _load()


def toggle(path: str, anchor: str = "", titre: str = "") -> bool:
    """Ajoute/supprime un favori. Retourne True si ajouté, False si retiré."""
    favs = _load()
    k = _key(path, anchor)
    if k in favs:
        favs.pop(k)
        _save(favs)
        return False
    favs[k] = {
        "path": path,
        "anchor": anchor,
        "titre": titre,
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save(favs)
    return True
