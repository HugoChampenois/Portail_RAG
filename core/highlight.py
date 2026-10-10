"""Surbrillance des termes d'une requête dans un texte (HTML `<mark>`)."""
from __future__ import annotations

import html
import re
from typing import List


def _escape(text: str) -> str:
    return html.escape(text or "", quote=False)


def highlight(text: str, terms: List[str]) -> str:
    """Retourne `text` (échappé HTML) avec les termes entourés de `<mark>`."""
    escaped = _escape(text)
    clean = [t for t in (terms or []) if t and len(t.strip()) > 1]
    if not clean:
        return escaped
    pattern = re.compile(
        "|".join(re.escape(_escape(t)) for t in clean),
        re.IGNORECASE,
    )
    return pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", escaped)


def query_terms(query: str) -> List[str]:
    return [w for w in re.split(r"\s+", (query or "").strip()) if len(w) > 1]
