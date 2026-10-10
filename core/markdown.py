"""Chargement (lazy) des fichiers Markdown du Vault consolidé.

Ne lit jamais tout le corpus en mémoire : un seul fichier à la fois, à la
demande. Gère le frontmatter YAML simple et l'extraction d'une section (ancre)
au sein d'un fichier de code consolidé.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional, Tuple

import config

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
HEADING_RE = re.compile(
    r"^#{1,6}\s+(.+?)(?:\s*\{#[^{}\n]+\})?\s*$", re.MULTILINE
)
TOC_HEADER_RE = re.compile(r"^##\s+(?:Sommaire|Procédure)\s*$", re.MULTILINE)
INTERNAL_LINK_RE = re.compile(r"\[\[#([^\]|]+?)(?:\|([^\]]+?))?\]\]")


def _parse_frontmatter(block: str) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key == "tags":
            try:
                meta[key] = json.loads(value)
            except json.JSONDecodeError:
                meta[key] = []
        else:
            meta[key] = value
    return meta


def read_markdown(rel_path: str) -> Tuple[Dict[str, Any], str]:
    """Lit un fichier du Vault -> (metadata, corps sans frontmatter)."""
    full = os.path.join(config.VAULT_DIR, rel_path)
    with open(full, encoding="utf-8") as handle:
        raw = handle.read()

    meta: Dict[str, Any] = {}
    body = raw
    m = FRONTMATTER_RE.match(raw)
    if m:
        meta = _parse_frontmatter(m.group(1))
        body = raw[m.end():]
    return meta, body


def extract_title(meta: Dict[str, Any], body: str) -> str:
    if meta.get("titre"):
        return meta["titre"]
    m = H1_RE.search(body or "")
    if m:
        return m.group(1).strip()
    m = HEADING_RE.search(body or "")
    return m.group(1).strip() if m else ""


def extract_section(body: str, anchor: str) -> Optional[str]:
    """Extrait la section contenant l'ancre `{#anchor}` d'un fichier consolidé."""
    if not anchor:
        return None
    for chunk in body.split("\n\n---\n\n"):
        if f"{{#{anchor}}}" in chunk:
            return chunk.strip()
    return None


def parse_toc(body: str) -> list:
    """Extrait le sommaire (liens `[[#ancre|libellé]]`) d'un fichier consolidé."""
    m = TOC_HEADER_RE.search(body or "")
    if not m:
        return []
    seg = body[m.end():]
    end = len(seg)
    cut = re.search(r"\n---\n|\n##\s+", seg)
    if cut:
        end = cut.start()
    entries = []
    seen = set()
    for lm in INTERNAL_LINK_RE.finditer(seg[:end]):
        anchor = lm.group(1)
        if anchor in seen:
            continue
        seen.add(anchor)
        entries.append({"anchor": anchor, "label": (lm.group(2) or anchor).strip()})
    return entries


def load(rel_path: str, anchor: Optional[str] = None) -> Dict[str, Any]:
    """Charge un document (ou une section) pour affichage.

    Retourne {meta, title, body, is_extract, rel_path, anchor}.
    """
    meta, body = read_markdown(rel_path)
    title = extract_title(meta, body)
    is_extract = False

    if anchor:
        section = extract_section(body, anchor)
        if section:
            body = section
            is_extract = True
            sec_title = extract_title({}, section)
            if sec_title:
                title = sec_title

    return {
        "meta": meta,
        "title": title,
        "body": body,
        "is_extract": is_extract,
        "rel_path": rel_path,
        "anchor": anchor,
    }
