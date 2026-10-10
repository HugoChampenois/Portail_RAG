"""Façade vers la canonicalisation des codes de `rag_droit.consolidate_vault`.

Le registre canonique des codes (CANON_CODES, CODE_ALIASES, résolution des
noms/variantes/annexes) est la source de vérité du générateur du Vault. Pour
éviter toute dérive entre le Vault et le portail, on importe directement les
fonctions du pipeline RAG Droit (lecture seule), qui ne dépendent que de la
stdlib.
"""
from __future__ import annotations

import os
import sys

_RAG_BASE = os.environ.get("PORTAIL_RAG_BASE", "/opt/rag")
if _RAG_BASE not in sys.path:
    sys.path.insert(0, _RAG_BASE)

try:
    from rag_droit.consolidate_vault import (  # noqa: E402
        CANON_CODES,
        CODE_ALIASES,
        canon_code_key,
        canon_key,
        classify,
        finance_domain,
        finance_year,
        juridiction_tag,
        load_links,
        norm_num,
        resolve_code_key,
        safe_id,
        slugify,
        specialite,
    )
    from rag_droit.router import MATIERE_FOLDER, RACINE_FOLDER  # noqa: E402
except Exception:  # noqa: BLE001 — portail utilisable même sans le pipeline RAG Droit
    CANON_CODES = {}
    CODE_ALIASES = {}
    MATIERE_FOLDER = {}
    RACINE_FOLDER = {}
    canon_key = lambda t: t or ""  # noqa: E731
    canon_code_key = lambda t: t or ""  # noqa: E731
    norm_num = lambda t: t or ""  # noqa: E731
    safe_id = lambda t: t or ""  # noqa: E731
    slugify = lambda t: t or ""  # noqa: E731

    def classify(record):  # noqa: ANN001
        return "skip", None

    def resolve_code_key(name):  # noqa: ANN001
        return None

    def specialite(tags):  # noqa: ANN001
        return "General"

    def juridiction_tag(tags):  # noqa: ANN001
        return "Autres"

    def finance_domain(titre):  # noqa: ANN001
        return None

    def finance_year(titre, date):  # noqa: ANN001
        return (date or "")[:4] or "sans_date"

    def load_links():  # noqa: ANN001
        return {}
