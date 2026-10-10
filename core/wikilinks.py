"""Parseur et résolveur de wikilinks Obsidian.

Formats réellement produits par le pipeline (voir `rag_droit/outputs.py` et
`rag_droit/consolidate_vault.py`) :

1. `[[Article 1382 du Code civil]]`          -> article de code (ancre)
2. `[[Code_civil#LEGIARTI…|Article 1382]]`   -> lien inter-codes (slug#ancre)
3. `[[#LEGIARTI…|Article 1382]]`             -> lien intra-code (même fichier)
4. `[[texte libre]]`                          -> référence (titre ou nom de code)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from core import index as idx

# Extraction des balises [[...]] (sans saut de ligne interne).
WIKILINK_RE = re.compile(r"\[\[([^\[\]\n]+?)\]\]")

# « Article X du Code Y »
ARTICLE_RE = re.compile(
    r"^(?:Article|Art\.?)\s+(?P<num>.+?)\s+du\s+(?P<code>code\s+.+)$", re.IGNORECASE
)


@dataclass
class Wikilink:
    raw: str
    target: str
    label: str
    kind: str = "free"  # 'article' | 'external' | 'internal' | 'free'
    code_name: Optional[str] = None
    num: Optional[str] = None
    slug: Optional[str] = None
    anchor: Optional[str] = None


def _parse_inner(inner: str) -> Wikilink:
    inner = inner.strip()
    if "|" in inner:
        target, label = inner.split("|", 1)
        target, label = target.strip(), label.strip()
    else:
        target, label = inner, inner

    link = Wikilink(raw=f"[[{inner}]]", target=target, label=label)

    if target.startswith("#"):
        link.kind = "internal"
        link.anchor = target[1:]
        if not label or label == target:
            link.label = link.anchor
        return link

    if "#" in target:
        link.kind = "external"
        link.slug, link.anchor = target.split("#", 1)
        if not label or label == target:
            link.label = link.anchor
        return link

    m = ARTICLE_RE.match(target)
    if m:
        link.kind = "article"
        link.num = m.group("num").strip()
        link.code_name = m.group("code").strip()
        return link

    link.kind = "free"
    return link


def find_wikilinks(text: str) -> List[Wikilink]:
    """Retourne tous les wikilinks du texte (ordre d'apparition, sans doublon)."""
    seen = set()
    links: List[Wikilink] = []
    for match in WIKILINK_RE.finditer(text or ""):
        link = _parse_inner(match.group(1))
        if link.raw in seen:
            continue
        seen.add(link.raw)
        links.append(link)
    return links


def resolve(link: Wikilink, current_path: Optional[str] = None) -> Optional[dict]:
    """Résout un wikilink vers {path, anchor, label} (ou None si introuvable)."""
    if link.kind == "internal":
        if not current_path:
            return None
        return {
            "path": current_path,
            "anchor": link.anchor,
            "label": link.label,
        }

    if link.kind == "external":
        code = idx.resolve_slug(link.slug or "")
        if not code:
            return None
        return {
            "path": code["path"],
            "anchor": link.anchor,
            "label": link.label,
        }

    if link.kind == "article":
        art = idx.resolve_article_by_code_name(link.code_name or "", link.num or "")
        if art:
            return {
                "path": art["path"],
                "anchor": art["anchor"],
                "label": link.label or f"Article {art['num_disp']} du {link.code_name}",
            }
        # Article introuvable : on retombe sur le fichier code complet.
        code = idx.resolve_code_name(link.code_name or "")
        if code:
            return {"path": code["path"], "anchor": None, "label": link.label}
        return None

    # free
    title = idx.resolve_free_title(link.target)
    if title:
        return {
            "path": title["path"],
            "anchor": title["anchor"],
            "label": link.label,
        }
    code = idx.resolve_code_name(link.target)
    if code:
        return {"path": code["path"], "anchor": None, "label": link.label}
    return None


def strip_anchor_marks(text: str) -> str:
    """Retire les marqueurs d'ancre `{#…}` des titres (affichage propre)."""
    return re.sub(r"\{#[A-Za-z0-9._/-]+\}", "", text or "")
