"""Accès (lecture seule) à l'index SQLite doc_id -> chemin dans le Vault.

L'index est construit une fois par `build_index.py` (lancé avec le venv du
portail, qui connaît `rag_droit`). Le portail n'a besoin que de `sqlite3`
(stdlib) pour l'interroger.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import Dict, List, Optional, Tuple

import config
from core.canon import canon_code_key
from core.normalize import canon, clean, norm_num

_conn: Optional[sqlite3.Connection] = None
_lock = threading.Lock()
_codes_cache = None


def get_connection() -> sqlite3.Connection:
    """Connexion SQLite partagée (lecture seule)."""
    global _conn
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(
                f"file:{config.INDEX_DB}?mode=ro", uri=True, check_same_thread=False
            )
            _conn.row_factory = sqlite3.Row
    return _conn


def is_built() -> bool:
    return os.path.exists(config.INDEX_DB)


def resolve_doc_id(doc_id: str) -> Optional[Dict[str, Optional[str]]]:
    """doc_id -> {path, anchor, type}."""
    if not doc_id:
        return None
    conn = get_connection()
    row = conn.execute(
        "SELECT path, anchor, type FROM docs WHERE id = ?", (doc_id,)
    ).fetchone()
    if not row:
        return None
    return {"path": row["path"], "anchor": row["anchor"], "type": row["type"]}


def get_types(doc_ids: List[str]) -> Dict[str, str]:
    """Type de document par doc_id (lookup par lot)."""
    ids = [i for i in doc_ids if i]
    if not ids:
        return {}
    conn = get_connection()
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT id, type FROM docs WHERE id IN ({placeholders})", ids
    ).fetchall()
    return {r["id"]: r["type"] for r in rows}


def get_doc_ids_by_type(types: List[str], limit: int) -> List[str]:
    """doc_ids d'un ou plusieurs types de document (ordre d'insertion)."""
    types = [t for t in types if t]
    if not types:
        return []
    conn = get_connection()
    placeholders = ",".join("?" for _ in types)
    rows = conn.execute(
        f"SELECT id FROM docs WHERE type IN ({placeholders}) LIMIT ?",
        [*types, limit],
    ).fetchall()
    return [r["id"] for r in rows]


def _load_codes():
    """Charge les codes en mémoire (petit : ~4k lignes) pour résolution rapide.

    Construit deux index : canon exact, et canon nettoyé (les noms issus du
    pipeline sont parfois pollués par de la ponctuation parasite). Pour le
    nettoyé, on privilégie les slugs qui contiennent réellement des articles
    (évite les « faux » codes générés par l'extraction gourmande).
    """
    global _codes_cache
    if _codes_cache is None:
        conn = get_connection()
        rows = conn.execute("SELECT slug, name, canon FROM codes").fetchall()
        slugs_with_art = {r[0] for r in conn.execute("SELECT DISTINCT code_slug FROM code_articles")}
        by_canon = {}
        by_clean = {}
        for r in rows:
            slug, name, canon_ = r["slug"], r["name"], r["canon"]
            by_canon.setdefault(canon_, (slug, name))
            by_clean.setdefault(clean(name), []).append((slug, name))
        for key in by_clean:
            by_clean[key].sort(key=lambda sn: 0 if sn[0] in slugs_with_art else 1)
        _codes_cache = (by_canon, by_clean)
    return _codes_cache


def resolve_code_name(code_name: str) -> Optional[Dict[str, str]]:
    """Nom de code (ex. « Code civil ») -> {slug, name, path}.

    Canonicalise le nom (annexes, alias, variantes) via le registre de
    `rag_droit`, puis résout par clé canonique exacte, avec repli sur le nom
    nettoyé.
    """
    if not code_name:
        return None
    by_canon, by_clean = _load_codes()
    hit = by_canon.get(canon_code_key(code_name))
    if hit is None:
        lst = by_clean.get(clean(code_name))
        if not lst:
            return None
        hit = lst[0]
    slug, name = hit
    return {"slug": slug, "name": name, "path": f"Codes/{slug}.md"}


def resolve_slug(slug: str) -> Optional[Dict[str, str]]:
    """slug (ex. « Code_civil ») -> {slug, name, path}."""
    conn = get_connection()
    row = conn.execute(
        "SELECT slug, name FROM codes WHERE slug = ?", (slug,)
    ).fetchone()
    if not row:
        return None
    return {"slug": row["slug"], "name": row["name"], "path": f"Codes/{row['slug']}.md"}


def resolve_article(code_slug: str, article_num: str) -> Optional[Dict[str, str]]:
    """(slug de code, n° d'article) -> {path, anchor, num_disp}."""
    key = norm_num(article_num)
    conn = get_connection()
    row = conn.execute(
        "SELECT anchor, num_disp FROM code_articles WHERE code_slug = ? AND num_norm = ?",
        (code_slug, key),
    ).fetchone()
    if not row:
        return None
    return {
        "path": f"Codes/{code_slug}.md",
        "anchor": row["anchor"],
        "num_disp": row["num_disp"] or article_num,
    }


def resolve_article_by_code_name(code_name: str, article_num: str) -> Optional[Dict[str, str]]:
    """« Article X du Code Y » -> {path, anchor, num_disp}.

    Cherche directement dans code_articles le numéro demandé, puis sélectionne
    le code dont la clé canonique correspond le mieux à `code_name`.
    """
    key = norm_num(article_num)
    conn = get_connection()
    rows = conn.execute(
        "SELECT a.code_slug, a.anchor, a.num_disp, c.canon "
        "FROM code_articles a LEFT JOIN codes c ON c.slug = a.code_slug "
        "WHERE a.num_norm = ?",
        (key,),
    ).fetchall()
    if not rows:
        return None

    target = canon_code_key(code_name)
    best = None
    best_score = -1
    for r in rows:
        rcanon = r["canon"] or ""
        if target and rcanon == target:
            score = 3
        elif target and (rcanon.startswith(target) or target.startswith(rcanon)):
            score = 2
        elif target and (target in rcanon or rcanon in target):
            score = 1
        else:
            score = 0
        if score > best_score:
            best_score = score
            best = r

    if best is None or best_score == 0:
        return None
    return {
        "path": f"Codes/{best['code_slug']}.md",
        "anchor": best["anchor"],
        "num_disp": best["num_disp"] or article_num,
    }


def resolve_free_title(title: str) -> Optional[Dict[str, str]]:
    """Texte libre [[...]] -> {path, anchor, type, titre}."""
    key = canon(title)
    conn = get_connection()
    row = conn.execute(
        "SELECT path, anchor, type, titre FROM titles WHERE norm = ?", (key,)
    ).fetchone()
    if not row:
        return None
    return {
        "path": row["path"],
        "anchor": row["anchor"],
        "type": row["type"],
        "titre": row["titre"],
    }


def list_code_articles(code_slug: str) -> List[Dict[str, str]]:
    """Sommaire d'un code : liste (num_disp, anchor, statut)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT num_disp, anchor, statut, date FROM code_articles "
        "WHERE code_slug = ? ORDER BY num_disp",
        (code_slug,),
    ).fetchall()
    return [
        {
            "num_disp": r["num_disp"] or "",
            "anchor": r["anchor"],
            "statut": r["statut"] or "",
            "date": r["date"] or "",
        }
        for r in rows
    ]


def get_tag_counts() -> List[Dict[str, str]]:
    """Facettes de tags : liste (tag, count, category), triée par catégorie puis count."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT tag, count, category FROM tag_counts ORDER BY category, count DESC"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [
        {"tag": r["tag"], "count": r["count"], "category": r["category"]} for r in rows
    ]


def get_backlinks(path: str, anchor: Optional[str] = None) -> List[Dict[str, str]]:
    """Documents qui référencent le document cible (liens inverses, dédupliqués)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT source_id, MIN(source_titre) AS source_titre FROM backlinks "
            "WHERE target_path = ? AND target_anchor = ? "
            "GROUP BY source_id LIMIT 200",
            (path, anchor or ""),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [
        {"source_id": r["source_id"], "source_titre": r["source_titre"] or ""}
        for r in rows
    ]


def suggest_titles(prefix: str, limit: int = 8) -> List[Dict[str, str]]:
    """Suggestions de titres pour l'autocomplétion (préfixe normalisé)."""
    prefix = (prefix or "").strip()
    if not prefix:
        return []
    key = canon(prefix)
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT norm, path, anchor, type, titre FROM titles "
            "WHERE norm LIKE ? ORDER BY length(norm) LIMIT ?",
            (key + "%", limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [
        {"titre": r["titre"], "path": r["path"], "anchor": r["anchor"], "type": r["type"]}
        for r in rows
    ]
