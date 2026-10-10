# Portail RAG — Base juridique DILA

Portail web local (Streamlit) pour consulter une base juridique massive :
- **recherche sémantique** (mode « Doctrine ») via Qdrant ;
- **navigation hypertexte** (mode « Wikipédia ») via le Vault Obsidian ;
- **assistant IA** (RAG) branché sur un LLM OpenAI-compatible.

Ce projet est **distinct** du pipeline de traitement [RAG Droit](https://github.com/HugoChampenois/Rag_Droit) : il se
branche en *lecture seule* sur ses sorties (Qdrant, `corpus_global.jsonl`,
`Vault_Obsidian/`) et construit son propre index local.

---

## Sommaire

1. [Vue d'ensemble](#vue-densemble)
2. [Prérequis](#prérequis)
3. [Architecture](#architecture)
4. [Flux de données](#flux-de-données)
5. [Installation](#installation)
6. [Lancement](#lancement)
7. [Fonctionnalités](#fonctionnalités)
8. [Composants (détail)](#composants-détail)
9. [Scripts de construction de l'index](#scripts-de-construction-de-lindex)
10. [Configuration](#configuration)
11. [Licences et mentions légales](#licences-et-mentions-légales)
12. [Améliorations futures](#améliorations-futures)

---

## Vue d'ensemble

| Besoin | Solution |
|---|---|
| Recherche sémantique | Qdrant (`rag_droit`, bge-m3) interrogé en direct |
| Embedding de la requête | Ollama local `bge-m3` (`localhost:11434`) |
| Rendu du document complet | Lecture lazy d'un fichier `.md` du Vault Obsidian |
| Résolution `doc_id → fichier` | Index SQLite local (`data/index.db`) |
| Liens hypertextes | Parseur de wikilinks Obsidian (`[[…]]`, `[[slug#ancre\|…]]`) |
| Filtres | Tags groupés + type de document (post-filtre + index) |
| Assistant IA | Client LLM OpenAI-compatible (configurable à chaud) |

---

## Prérequis

Le portail ne fonctionne qu'en présence du **pipeline RAG Droit** et de ses
sorties (voir le dépôt `Rag_Droit`) :

- **Qdrant** sur `localhost:6333` (collection `rag_droit`) ;
- **Ollama** sur `localhost:11434` avec le modèle `bge-m3` ;
- le **Vault Obsidian** généré (racine configurable via `PORTAIL_VAULT_DIR`) ;
- le **corpus JSONL** (`corpus_global.jsonl`) pour construire l'index local.

Par défaut, le pipeline est supposé installé dans `/opt/rag` ; surchargez ce
chemin avec la variable `PORTAIL_RAG_BASE` (voir [Configuration](#configuration)).

---

## Architecture

```
portail_rag/
├── app.py                 # Point d'entrée Streamlit (routing + sidebar)
├── config.py              # Chemins, URLs Qdrant/Ollama, réglages
├── requirements.txt       # streamlit, qdrant-client, httpx
├── build_index.py         # Construit data/index.db (doc_id → chemin/ancre)
├── build_extras.py        # Complète l'index : tag_counts + backlinks
│
├── core/                  # Logique métier (aucune dépendance Streamlit)
│   ├── embedder.py        #   Embedding des requêtes via Ollama (bge-m3)
│   ├── search.py          #   Recherche Qdrant + filtres tags/type
│   ├── index.py           #   Accès SQLite (résolution doc_id, codes, backlinks…)
│   ├── wikilinks.py       #   Parseur/résolveur de wikilinks Obsidian
│   ├── markdown.py        #   Chargement lazy des .md + extraction sommaire/ancre
│   ├── normalize.py       #   Normalisation de chaînes (accents, n° d'article)
│   ├── canon.py           #   Façade vers rag_droit (registre canonique des codes)
│   ├── favorites.py       #   Favoris persistants (JSON)
│   ├── highlight.py       #   Surbrillance des termes de la requête
│   ├── llm.py             #   Client LLM OpenAI-compatible (+ streaming)
│   └── rag.py             #   Chaîne RAG (récupération + prompts)
│
├── ui/                    # Interface Streamlit
│   ├── home.py            #   Page Recherche (barre, filtres, cartes, pagination)
│   ├── document.py        #   Lecture d'un document (wikilinks, backlinks, résumé)
│   ├── navigation.py      #   État de session (pages, historique, retour)
│   ├── favorites_view.py  #   Page Favoris
│   ├── settings.py        #   Page Paramètres IA
│   └── chat.py            #   Page Assistant IA (chat RAG)
│
└── data/                  # Généré au runtime
    ├── index.db           #   Index SQLite (docs, codes, code_articles, titles…)
    ├── favorites.json     #   Favoris
    └── llm_config.json    #   Configuration du LLM
```

---

## Flux de données

```
<RAG_BASE>/donnees_traitees/corpus_global.jsonl      (source de vérité)
        │
        ├──► build_index.py ──► data/index.db
        │        ├── docs           (id → path, ancre, type)
        │        ├── codes          (registre canonique des codes)
        │        ├── code_articles  (code_slug + n° → ancre)
        │        └── titles         (titre normalisé → chemin)
        │
        └──► build_extras.py ──► data/index.db
                 ├── tag_counts     (facettes de tags)
                 └── backlinks      (graphe inversé des références)

<RAG_BASE>/Vault_Obsidian/*.md                    (fichiers consolidés, lecture seule)
        │   Codes/Code_<nom>.md, Lois/{YYYY}.md,
        │   JP/Inedites/{Matiere}/{YYYY}.md, JP/Publiees/{Juridiction}/{Pourvoi}.md
        └──► core/markdown.py (chargement lazy d'un fichier à la fois)

Qdrant (rag_droit)  ──► core/search.py (requête vectorielle + filtres)
Ollama (bge-m3)     ──► core/embedder.py (embedding de la requête)
```

---

## Installation

```bash
git clone https://github.com/HugoChampenois/Portail_RAG.git
cd Portail_RAG
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

---

## Lancement

```bash
venv/bin/streamlit run app.py --server.port 8501 --server.headless true
```

Accès : `http://localhost:8501` (ou `http://<IP>:8501`).

---

## Fonctionnalités

### Page « Recherche »
- **Recherche sémantique** : requête vectorielle (bge-m3) sur Qdrant, résultats
  dédupliqués par document, triés par similarité.
- **Filtres par tags** (groupés + compteurs) : `Racine`, `Juridiction`, `Matière`,
  `Statut`, `Autres`. Sémantique : **OU** au sein d'une catégorie, **ET** entre
  catégories.
- **Filtre « Type de document »** : Code / Lois et règlements / Jurisprudence
  (inédite) / Jurisprudence (publiée).
- **Recherche par tags seuls** (sans mots-clés) et par type seul.
- **Surbrillance** des termes de la requête dans les extraits.
- **Autocomplétion** des titres pendant la saisie.
- **Pagination** des résultats (10/page).

### Lecture d'un document
- Rendu Markdown avec **wikilinks transformés en boutons** cliquables.
- Pour les fichiers consolidés (code, lois, jurisprudence, procédure) : **lecteur
  à sommaire filtrable** (évite de rendre des fichiers de plusieurs Mo).
- **Extraction d'ancre** : navigation directe vers un article/section.
- **Backlinks** (« Référencé par ») : documents qui citent le document courant.
- **Favoris** (étoile ☆) persistants.
- **Résumé** du document via le LLM (si configuré).

### Assistant IA (page séparée)
- Chat RAG : récupération de contexte (top-k) puis génération streaming, avec
  **sources citées cliquables**.
- **Paramètres IA** : choix du fournisseur (API externe, DeepSeek, Mistral,
  vLLM distant, Ollama local), URL, modèle, clé — persistés dans
  `data/llm_config.json`.

---

## Composants (détail)

### `core/embedder.py`
Client d'embedding de requête via **Ollama** (`POST /api/embed`, modèle `bge-m3`).
Retourne un vecteur par texte. `EmbedError` si Ollama est injoignable.

### `core/search.py`
Recherche sémantique directe dans Qdrant. Trois chemins :
- `search()` : requête vectorielle (`query_points`) + filtre tags (`Filter` sur le
  champ payload `tags`), déduplication par `doc_id`, post-filtre par type ;
- `search_by_tags()` : scroll filtré (recherche par tags seuls) ;
- `search_by_type()` : résolution par l'index + `retrieve` Qdrant (recherche par
  type seul, car le scroll Qdrant est clusterisé par source).

### `core/index.py`
Accès (lecture seule) à `data/index.db`. Principales fonctions :
- `resolve_doc_id(id)` → `{path, anchor, type}` ;
- `resolve_code_name(nom)` / `resolve_slug(slug)` → fichier de code ;
- `resolve_article_by_code_name(nom, n°)` → ancre d'un article de code ;
- `get_tag_counts()`, `get_backlinks()`, `suggest_titles()`, `get_types()`,
  `get_doc_ids_by_type()`, `list_code_articles()`.

### `core/wikilinks.py`
Parseur des wikilinks Obsidian produits par le pipeline. Quatre formats gérés :
1. `[[Article 1382 du Code civil]]` → article de code (ancre) ;
2. `[[Code_civil#LEGIARTI…|Article 1382]]` → lien inter-codes ;
3. `[[#LEGIARTI…|Article 1382]]` → lien intra-fichier ;
4. `[[texte libre]]` → référence (résolue par titre ou nom de code).

### `core/markdown.py`
Chargement **lazy** d'un fichier `.md` (un seul à la fois, jamais tout le corpus
en RAM). Parse le frontmatter YAML, extrait une section par ancre (`{#…}`), et
extrait le sommaire (`parse_toc`) des fichiers consolidés.

### `core/canon.py`
Façade qui importe **au runtime** les fonctions de canonicalisation de
`rag_droit.consolidate_vault` (`CANON_CODES`, `CODE_ALIASES`, `resolve_code_key`,
`slugify`, …). Garantit que les chemins/ancres du portail coïncident exactement
avec le générateur du Vault. Dégradation gracieuse si le pipeline RAG Droit est
absent.

### `core/favorites.py`
Favoris persistants dans `data/favorites.json`, identifiés par `path#anchor`.

### `core/llm.py` / `core/rag.py`
- `llm.py` : client **OpenAI-compatible** (`/v1/chat/completions`), génération
  **streaming** ou complète, configuration chargée de `data/llm_config.json`.
- `rag.py` : prompt système d'assistant juridique, construction du contexte
  (borné en taille) à partir des documents récupérés, prompt de résumé.

### `ui/navigation.py`
État de session centralisé (`st.session_state`) : page courante, document
courant, pile d'historique (bouton Retour), résultats de recherche conservés.

---

## Scripts de construction de l'index

L'index doit être **reconstruit** chaque fois que le Vault Obsidian est régénéré
(structure/chemins modifiés) ou que `corpus_global.jsonl` change.

```bash
venv/bin/python build_index.py     # ~4 min : docs, codes, code_articles, titles
venv/bin/python build_extras.py    # ~3 min : tag_counts + backlinks
```

- `build_index.py` réplique la logique de chemin du
  `consolidate_vault.py` du pipeline (codes canoniques, lois par année, JP inédite
  par matière/année, JP publiée par juridiction/pourvoi, CAPP liés fusionnés).
- `build_extras.py` scanne le `markdown` du JSONL pour compter les tags et
  construire le graphe de backlinks (résolution des visas
  `[[Article X du Code Y]]`).

> Les deux scripts utilisent le mode **WAL** (SQLite) : sûrs contre les
> interruptions (un `kill` ne corrompt pas l'index).

---

## Configuration

Toutes les variables sont surchargeables par variables d'environnement :

| Variable | Défaut | Rôle |
|---|---|---|
| `PORTAIL_RAG_BASE` | `/opt/rag` | Racine du pipeline RAG Droit |
| `PORTAIL_VAULT_DIR` | `<RAG_BASE>/Vault_Obsidian` | Racine du Vault |
| `PORTAIL_JSONL` | `<RAG_BASE>/donnees_traitees/corpus_global.jsonl` | Corpus JSONL (build) |
| `PORTAIL_QDRANT_URL` | `http://localhost:6333` | Serveur Qdrant |
| `PORTAIL_COLLECTION` | `rag_droit` | Collection Qdrant |
| `PORTAIL_OLLAMA_URL` | `http://localhost:11434` | Serveur d'embedding |
| `PORTAIL_EMBED_MODEL` | `bge-m3` | Modèle d'embedding |
| `PORTAIL_INDEX_DB` | `data/index.db` | Chemin de l'index SQLite |
| `PORTAIL_SEARCH_LIMIT` | `10` | Résultats par défaut |
| `PORTAIL_RAG_TOP_K` | `5` | Documents récupérés pour le contexte IA |
| `PORTAIL_RAG_CONTEXT_CHARS` | `12000` | Taille max du contexte LLM |

La configuration du LLM (`data/llm_config.json`) se gère depuis la page
« Paramètres IA ».

---

## Licences et mentions légales

- **Ce dépôt (code source)** est distribué sous licence **MIT** — voir `LICENSE`.
- **Qdrant** (base de données vectorielle) est © Qdrant Solutions GmbH et est
  distribué sous **Apache License 2.0** — voir `THIRD_PARTY_LICENSES` et
  <https://www.apache.org/licenses/LICENSE-2.0>.
- **Streamlit** (framework d'interface) est distribué sous **Apache License 2.0**.
- **Ollama** (serveur de modèles local) est distribué sous licence **MIT**.
- **Les données juridiques** (LEGI, CASS, CAPP, CONSTIT, JADE) sont des données
  publiques produites par la **DILA** et mises à disposition sous **Licence
  Ouverte** (Etalab). Elles ne sont pas incluses dans ce dépôt.

---

## Améliorations futures

### Recherche & indexation
- **Payload index / filtres plus rapides** : les filtres par tag actuels lisent
  les payloads depuis le disque (`on_disk_payload=true`), d'où ~8 s de latence.
  Piste : indexer les payloads en mémoire ou créer un payload index Qdrant sur le
  champ `tags`.
- **Recherche hybride** (dense + BM25) : combiner le vectoriel avec du
  plein-texte pour les requêtes très précises (n° d'article, NOR…).
- **Index incrémental** : reconstruire seulement les documents modifiés au lieu
  d'un scan complet du JSONL (~7 min).
- **Reranking** : re-trier les top-k avec un cross-encoder pour affiner la
  pertinence.

### Interface / UX
- **Pagination continue** (infinite scroll) au lieu de « Précédent/Suivant ».
- **Mode sombre / thème** et mise en page des cartes (miniatures, extraits plus
  longs).
- **Export** du document (Markdown/PDF) et copie de citation.
- **Recherche avancée** : plage de dates, juridiction/matière combinées avec
  plus de granularité, tri configurable (pertinence / date / statut).
- **Filtre par année** (les lois et JP inédites sont déjà regroupées par année).

### Navigation / hypertexte
- **Vue « backlinks » dédiée** (graphe de citations, comme Obsidian).
- **Sommaire flottant** (TOC latéral) avec surlignage de la section courante.
- **Fil d'Ariane cliquable** et historique complet (avant/après), pas seulement
  « Retour ».
- **Recommandations** (« documents similaires ») par similarité vectorielle.

### Assistant IA
- **Streaming token par token** déjà en place ; ajouter le **streaming des
  sources** au fil de la génération.
- **Citations structurées** (extraits exacts + n° de ligne), pas seulement la
  liste des sources.
- **Mémoire de conversation** persistante (par session/thème).
- **Résumé de fichier consolidé entier** (gestion de contexte long / map-reduce).

### Robustesse & opérations
- **Tests unitaires** sur les parseurs/résolveurs (wikilinks, index) en plus des
  tests `AppTest`.
- **Conteneurisation** (Docker) du portail pour un déploiement reproductible.
- **Métriques/logs** : temps de recherche, taux de cache, erreurs Qdrant/Ollama.

---

## Notes de maintenance

- Le portail est **couplé au format du Vault** généré par
  `rag_droit.consolidate_vault`. Toute évolution de ce format doit être
  répercutée dans `build_index.py`, `core/canon.py`, `core/wikilinks.py`.
- `core/canon.py` importe `rag_droit` au runtime : si le pipeline RAG Droit est
  déplacé, renseignez `PORTAIL_RAG_BASE` en conséquence.
