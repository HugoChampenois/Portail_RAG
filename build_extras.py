"""Construit les tables complémentaires de l'index : tag_counts et backlinks.

À lancer APRÈS build_index.py (qui crée docs/codes/code_articles/titles) :

    venv/bin/python build_extras.py

- `tag_counts` : facettes de tags (tag -> nombre de documents + catégorie).
- `backlinks`  : graphe inversé (quel document référence quel article de code).

Les wikilinks du JSONL sont de deux formes : `[[Article X du Code Y]]` (visas,
résolus ici) et `[[texte libre]]` (références, ignorées). On n'utilise qu'une
seule regex ciblée (rapide) et on commit par lots pour la reprise.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.canon import canon_code_key, norm_num  # noqa: E402

JSONL_PATH = os.environ.get(
    "PORTAIL_JSONL",
    os.path.join(os.environ.get("PORTAIL_RAG_BASE", "/opt/rag"), "donnees_traitees", "corpus_global.jsonl"),
)
INDEX_DB = os.environ.get("PORTAIL_INDEX_DB", os.path.join(BASE_DIR, "data", "index.db"))

BATCH = 20000
COMMIT_EVERY = 100000

# « [[Article X du Code Y]] » uniquement.
ARTICLE_LINK_RE = re.compile(
    r"\[\[(?:Article|Art\.?)\s+(.+?)\s+du\s+(Code\s+[^\]]+?)\]\]", re.IGNORECASE
)

RACINE = {"droit_prive", "droit_public", "droit_penal"}
JURIDICTION = {
    "cass", "cass_soc", "cass_com", "cass_crim", "cass_civ1", "cass_civ2", "cass_civ3",
    "cass_civ", "cass_ap", "cass_mixte", "cass_chambres_reunies", "cass_avis", "cass_crd",
    "cour_appel", "cour_admin_appel", "conseil_constitutionnel", "conseil_etat",
    "tribunal_conflits", "tribunal_administratif", "conseil_prudhommes",
    "tribunal_commerce", "tribunal_judiciaire", "juridiction_inconnue",
}
STATUT = {
    "cassation_partielle_sans_renvoi", "cassation_partielle", "cassation_sans_renvoi",
    "cassation", "irrecevabilite", "desistement", "satisfaction_totale",
    "satisfaction_partielle", "annulation_partielle", "annulation_totale", "reformation",
    "decharge", "annulation", "non_conformite_totale", "non_conformite_partielle",
    "non_conformite", "conformite_reserve", "conformite", "ineligibilite", "non_lieu",
    "decheance", "qpc", "avis", "confirme", "infirme", "rejet",
    "vigueur", "abroge", "abroge_differe", "modifie", "perime", "remis_en_vigueur",
}


def classify_tag(tag: str) -> str:
    if tag.startswith("article_"):
        return "article"  # bruit (un tag par n° d'article), exclu des facettes
    if tag in RACINE:
        return "racine"
    if tag in JURIDICTION:
        return "juridiction"
    if tag in STATUT:
        return "statut"
    if tag.startswith("droit_") or tag.startswith("procedure_"):
        return "matiere"
    return "autres"


def iter_jsonl(path: str):
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
    conn = sqlite3.connect(INDEX_DB)
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA cache_size = -200000")

    conn.executescript(
        """
        DROP TABLE IF EXISTS tag_counts;
        DROP TABLE IF EXISTS backlinks;
        CREATE TABLE tag_counts (tag TEXT PRIMARY KEY, count INTEGER, category TEXT);
        CREATE TABLE backlinks (
            target_path TEXT NOT NULL,
            target_anchor TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_titre TEXT
        );
        """
    )
    conn.commit()

    codes = conn.execute("SELECT slug, name, canon FROM codes").fetchall()
    slug_canon = {slug: canon for slug, name, canon in codes}

    by_num = defaultdict(list)
    for slug, nn, anchor in conn.execute(
        "SELECT code_slug, num_norm, anchor FROM code_articles"
    ):
        by_num[nn].append((slug, anchor))

    def resolve_article(code_name: str, num: str):
        cands = by_num.get(norm_num(num))
        if not cands:
            return None
        target = canon_code_key(code_name)
        best, best_score = None, -1
        for slug, anchor in cands:
            cc = slug_canon.get(slug, "")
            if target and cc == target:
                score = 3
            elif target and (cc.startswith(target) or target.startswith(cc)):
                score = 2
            elif target and (target in cc or cc in target):
                score = 1
            else:
                score = 0
            if score > best_score:
                best_score, best = score, (slug, anchor)
        if best is None or best_score == 0:
            return None
        return f"Codes/{best[0]}.md", best[1]

    tag_count = defaultdict(int)
    backlink_buf = []
    count = 0

    for record in iter_jsonl(JSONL_PATH):
        doc_id = record.get("id")
        titre = record.get("titre", "") or ""
        for tag in record.get("tags", []) or []:
            if not tag.startswith("article_"):
                tag_count[tag] += 1

        markdown = record.get("markdown", "") or ""
        if doc_id and "[[" in markdown:
            for m in ARTICLE_LINK_RE.finditer(markdown):
                target = resolve_article(m.group(2), m.group(1))
                if target:
                    backlink_buf.append((target[0], target[1] or "", doc_id, titre))

        count += 1
        if len(backlink_buf) >= BATCH:
            conn.executemany(
                "INSERT INTO backlinks(target_path, target_anchor, source_id, source_titre) "
                "VALUES (?,?,?,?)",
                backlink_buf,
            )
            backlink_buf.clear()
        if count % COMMIT_EVERY == 0:
            conn.commit()
            print(f"[extras] {count} enregistrements… ({time.time()-start:.0f}s)", file=sys.stderr)

    if backlink_buf:
        conn.executemany(
            "INSERT INTO backlinks(target_path, target_anchor, source_id, source_titre) "
            "VALUES (?,?,?,?)",
            backlink_buf,
        )
        backlink_buf.clear()

    conn.executemany(
        "INSERT INTO tag_counts(tag, count, category) VALUES (?,?,?)",
        [(t, c, classify_tag(t)) for t, c in tag_count.items()],
    )
    conn.execute("CREATE INDEX idx_backlinks ON backlinks(target_path, target_anchor)")
    conn.commit()
    conn.execute("PRAGMA optimize")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.close()

    print(f"[extras] terminé en {time.time()-start:.0f}s -> {INDEX_DB}", file=sys.stderr)


if __name__ == "__main__":
    build()
