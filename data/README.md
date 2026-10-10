# `data/` — Fichiers générés

Ce dossier contient les artefacts locaux du portail, créés au runtime ou par les
scripts de construction. **Tout est régénérable** (sauf les préférences
utilisateur).

| Fichier | Créé par | Rôle |
|---|---|---|
| `index.db` | `build_index.py` + `build_extras.py` | Index SQLite (résolution, codes, tags, backlinks) |
| `favorites.json` | `core/favorites.py` | Favoris utilisateur (persistants) |
| `llm_config.json` | `core/llm.py` (page Paramètres IA) | Configuration du LLM |

---

## `index.db` — schéma SQLite

### `docs`
Mapping **`doc_id → emplacement dans le Vault`** (2,9 M lignes).

| Colonne | Type | Description |
|---|---|---|
| `id` | TEXT (PK) | Identifiant du document (LEGIARTI…, JURITEXT…, n° de pourvoi…) |
| `path` | TEXT | Chemin relatif du fichier dans `Vault_Obsidian/` |
| `anchor` | TEXT | Ancre `{#…}` dans le fichier consolidé (ou NULL) |
| `type` | TEXT | `code` \| `lois_reglements` \| `jurisprudence` \| `procedure` |

Convention d'ancre :
- **code** : ancre = `id` **brut** (`LEGIARTI…`) ;
- **lois / JP** : ancre = `safe_id(id)` (caractères non alphanumériques → `_`).

### `codes`
Registre canonique des codes (60 lignes).

| Colonne | Type | Description |
|---|---|---|
| `slug` | TEXT (PK) | Nom de fichier (`Code_civil`, …) |
| `name` | TEXT | Nom lisible (`Code civil`, …) |
| `canon` | TEXT | Clé canonique (`code civil`, …) |

### `code_articles`
Articles de codes consolidés (259 k lignes, 1 par `(code_slug, num)` dédupliqué).

| Colonne | Type | Description |
|---|---|---|
| `code_slug` | TEXT | Slug du code parent |
| `num_norm` | TEXT | Numéro normalisé (pour correspondance) |
| `num_disp` | TEXT | Numéro affiché (`1382`, `L. 1152-2`…) |
| `anchor` | TEXT | `id` brut de l'article (ancre dans le fichier code) |
| `statut` | TEXT | `vigueur`, `abroge`, `modifie`… |
| `date` | TEXT | Date de vigueur |

### `titles`
Titre normalisé → emplacement (2,2 M lignes, dédupliqué par titre).

| Colonne | Type | Description |
|---|---|---|
| `norm` | TEXT (PK) | Titre normalisé (minuscules, sans accents) |
| `path` / `anchor` / `type` | — | Emplacement du « meilleur » doc portant ce titre |
| `titre` | TEXT | Titre d'origine (affichage) |

### `tag_counts`
Facettes de tags pour les filtres (123 lignes).

| Colonne | Type | Description |
|---|---|---|
| `tag` | TEXT (PK) | Tag (`cass_soc`, `droit_civil`, `rejet`…) |
| `count` | INT | Nombre de documents |
| `category` | TEXT | `racine` \| `juridiction` \| `matiere` \| `statut` \| `autres` |

> Les tags `article_*` (un par numéro d'article) sont exclus car trop granulaires.

### `backlinks`
Graphe inversé des références (7,2 M lignes).

| Colonne | Type | Description |
|---|---|---|
| `target_path` | TEXT | Chemin du document cible |
| `target_anchor` | TEXT | Ancre cible |
| `source_id` | TEXT | Identifiant du document qui cite |
| `source_titre` | TEXT | Titre du document source |

> Construit uniquement à partir des visas `[[Article X du Code Y]]` présents
> dans le `markdown` du JSONL. Les références libres (`[[texte]]`) ne sont pas
> résolues.

---

## Régénération

```bash
cd ..   # racine du projet
venv/bin/python build_index.py     # recrée index.db (docs, codes, code_articles, titles)
venv/bin/python build_extras.py    # ajoute tag_counts + backlinks
```

Suppression manuelle : `rm -f data/index.db data/favorites.json data/llm_config.json`
(les favoris et la config LLM sont alors perdus — sauvegardez-les si besoin).
