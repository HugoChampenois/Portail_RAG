"""Construit l'index SQLite doc_id -> chemin dans le Vault consolidé.

Réplique fidèlement la logique de chemin du nouveau `consolidate_vault.py` :
    Codes/Code_<nom>.md, Lois/{YYYY}.md (+Finances/Securite_Sociale),
    JP/Inedites/{Matiere}/{YYYY}.md, JP/Publiees/{Juridiction}/{Pourvoi}.md.

Lancement (venv du portail ; importe rag_droit via core.canon) :
    venv/bin/python build_index.py

Sortie : data/index.db.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from typing import Any, Dict, Iterator, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.canon import (  # noqa: E402
    CANON_CODES,
    canon_key,
    classify,
    finance_domain,
    finance_year,
    juridiction_tag,
    load_links,
    norm_num,
    safe_id,
    slugify,
    specialite,
)

JSONL_PATH = os.environ.get(
    "PORTAIL_JSONL",
    os.path.join(os.environ.get("PORTAIL_RAG_BASE", "/opt/rag"), "donnees_traitees", "corpus_global.jsonl"),
)
INDEX_DB = os.environ.get("PORTAIL_INDEX_DB", os.path.join(BASE_DIR, "data", "index.db"))

BATCH = 5000
_FINANCE_SUBDIR = {"finances": "Finances", "securite_sociale": "Securite_Sociale"}


def iter_jsonl(path: str) -> Iterator[Dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def build() -> None:
    start = time.time()
    os.makedirs(os.path.dirname(INDEX_DB), exist_ok=True)
    if os.path.exists(INDEX_DB):
        os.remove(INDEX_DB)

    # --- Liens CASS -> CAPP (procédures publiées) ---
    cass_to_capp = load_links()
    reverse: Dict[str, str] = {}
    for cass_id, capp_ids in cass_to_capp.items():
        for cid in capp_ids:
            reverse[cid] = cass_id
    linked_capp = set(reverse)

    conn = sqlite3.connect(INDEX_DB)
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA cache_size = -200000")

    conn.executescript(
        """
        CREATE TABLE docs (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            anchor TEXT,
            type TEXT
        );
        CREATE TABLE codes (
            slug TEXT PRIMARY KEY,
            name TEXT,
            canon TEXT
        );
        CREATE TABLE code_articles_raw (
            code_slug TEXT NOT NULL,
            num_norm TEXT NOT NULL,
            num_disp TEXT,
            anchor TEXT NOT NULL,
            statut TEXT,
            date TEXT
        );
        CREATE TABLE titles_raw (
            norm TEXT NOT NULL,
            path TEXT NOT NULL,
            anchor TEXT,
            type TEXT,
            titre TEXT,
            statut TEXT,
            date TEXT
        );
        """
    )

    docs_buf = []
    codes = {}          # code_key -> (slug, name)
    art_buf = []
    titles_buf = []
    root_jur = {}       # id_cass -> juridiction (racines publiées)
    pending = []        # (doc_id, titre, statut, date) — CAPP liés, résolus en fin

    def flush():
        if docs_buf:
            conn.executemany(
                "INSERT OR REPLACE INTO docs(id, path, anchor, type) VALUES (?,?,?,?)",
                docs_buf,
            )
            docs_buf.clear()
        if art_buf:
            conn.executemany(
                "INSERT INTO code_articles_raw(code_slug, num_norm, num_disp, anchor, statut, date) "
                "VALUES (?,?,?,?,?,?)",
                art_buf,
            )
            art_buf.clear()
        if titles_buf:
            conn.executemany(
                "INSERT INTO titles_raw(norm, path, anchor, type, titre, statut, date) "
                "VALUES (?,?,?,?,?,?,?)",
                titles_buf,
            )
            titles_buf.clear()
        conn.commit()

    count = 0
    for record in iter_jsonl(JSONL_PATH):
        doc_id = record.get("id")
        if not doc_id:
            continue
        category, code_key = classify(record)
        tags = record.get("tags", [])
        titre = record.get("titre", "") or ""
        num = (record.get("num") or "").strip()
        statut = record.get("statut", "") or ""
        date = record.get("date", "") or ""
        annee = date[:4] or "sans_date"

        art_entry = None
        if category == "code_article":
            name = CANON_CODES.get(code_key, code_key)
            slug = slugify(name)
            codes.setdefault(code_key, (slug, name))
            path = f"Codes/{slug}.md"
            anchor = doc_id          # ancre = id brut (LEGIARTI…)
            type_ = "code"
            if num:
                art_entry = (slug, norm_num(num), num, doc_id, statut, date)
        elif category in ("tnc_container", "tnc_article"):
            domaine = finance_domain(titre)
            grp_annee = finance_year(titre, date) if domaine else annee
            subdir = _FINANCE_SUBDIR.get(domaine, "")
            path = f"Lois/{subdir}/{grp_annee}.md" if subdir else f"Lois/{grp_annee}.md"
            anchor = safe_id(doc_id)
            type_ = "lois_reglements"
        elif category == "jp":
            if "arret_de_principe" in tags:
                jur = juridiction_tag(tags)
                root_jur[doc_id] = jur
                path = f"JP/Publiees/{jur}/{safe_id(doc_id)}.md"
                anchor = safe_id(doc_id)
                type_ = "procedure"
            elif doc_id in linked_capp:
                pending.append((doc_id, titre, statut, date))
                count += 1
                continue
            else:
                matiere = specialite(tags)
                path = f"JP/Inedites/{matiere}/{annee}.md"
                anchor = safe_id(doc_id)
                type_ = "jurisprudence"
        else:
            continue  # code_container / struct

        docs_buf.append((doc_id, path, anchor, type_))
        if art_entry is not None:
            art_buf.append(art_entry)
        titles_buf.append((canon_key(titre), path, anchor, type_, titre, statut, date))

        count += 1
        if len(docs_buf) >= BATCH:
            flush()
            if count % 200000 == 0:
                print(f"[index] {count} enregistrements… ({time.time()-start:.0f}s)", file=sys.stderr)

    # Résolution des CAPP liés : fichier de la procédure de leur pourvoi (CASS).
    for doc_id, titre, statut, date in pending:
        root = reverse.get(doc_id)
        if not root:
            continue
        jur = root_jur.get(root, "Autres")
        path = f"JP/Publiees/{jur}/{safe_id(root)}.md"
        anchor = safe_id(doc_id)
        docs_buf.append((doc_id, path, anchor, "procedure"))
        titles_buf.append((canon_key(titre), path, anchor, "procedure", titre, statut, date))

    flush()

    conn.executemany(
        "INSERT OR REPLACE INTO codes(slug, name, canon) VALUES (?,?,?)",
        [(s, n, c) for c, (s, n) in codes.items()],
    )
    conn.commit()

    print("[index] déduplication (best par article/titre)…", file=sys.stderr)
    conn.executescript(
        """
        CREATE INDEX idx_art ON code_articles_raw(code_slug, num_norm);
        CREATE INDEX idx_titles ON titles_raw(norm);

        CREATE TABLE code_articles (
            code_slug TEXT NOT NULL,
            num_norm TEXT NOT NULL,
            num_disp TEXT,
            anchor TEXT NOT NULL,
            statut TEXT,
            date TEXT
        );
        INSERT INTO code_articles (code_slug, num_norm, num_disp, anchor, statut, date)
        SELECT code_slug, num_norm, num_disp, anchor, statut, date FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY code_slug, num_norm
                ORDER BY (statut='vigueur') DESC, date DESC, anchor
            ) AS rn FROM code_articles_raw
        ) WHERE rn = 1;
        DROP TABLE code_articles_raw;

        CREATE TABLE titles (
            norm TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            anchor TEXT,
            type TEXT,
            titre TEXT
        );
        INSERT INTO titles (norm, path, anchor, type, titre)
        SELECT norm, path, anchor, type, titre FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY norm
                ORDER BY (statut='vigueur') DESC, date DESC, anchor
            ) AS rn FROM titles_raw
        ) WHERE rn = 1;
        DROP TABLE titles_raw;

        CREATE INDEX idx_code_articles ON code_articles(code_slug, num_norm);
        """
    )
    conn.commit()
    conn.execute("PRAGMA optimize")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.close()

    print(f"[index] terminé en {time.time()-start:.0f}s -> {INDEX_DB}", file=sys.stderr)


if __name__ == "__main__":
    build()
