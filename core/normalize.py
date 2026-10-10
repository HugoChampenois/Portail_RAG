"""Normalisation de chaînes pour la résolution des wikilinks.

Réplique fidèle de la logique de `rag_droit.consolidate_vault` (fold_accents,
norm_num, canon_key) afin que la résolution côté portail corresponde exactement
aux fichiers/noms générés par le pipeline.
"""
from __future__ import annotations

import unicodedata


def fold_accents(text: str) -> str:
    """Supprime les accents et met en minuscules."""
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


def canon(text: str) -> str:
    """Clé canonique : minuscules, sans accents, espaces unifiés."""
    return " ".join(fold_accents(text).split())


def norm_num(num: str) -> str:
    """Normalise un numéro d'article (L. 1234-1 == L1234-1)."""
    s = fold_accents(num or "")
    s = s.replace(" ", "").replace(".", "").replace("\u00a0", "")
    return s


_PUNCT = " \t\r\n().,;:«»\"''—–-–"


def clean(text: str) -> str:
    """Nettoie un libellé (nom de code) : casse, accents, ponctuation de bord."""
    s = fold_accents(text or "").strip(_PUNCT)
    return " ".join(s.split())
