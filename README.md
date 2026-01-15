# Tolkien_KG (Semantic Web Project)

This project builds a Knowledge Graph (KG) from **Tolkien Gateway** pages, exposes it via **Apache Jena Fuseki (SPARQL endpoint)**, validates extracted data with **SHACL shapes derived from wiki templates**, and provides a **Linked Data interface** (HTML + Turtle) inspired by **DBpedia**.

---

## 1) What this KG contains

### Core ideas
- **Each Tolkien Gateway wiki page → one KG entity** (`/resource/<Title>`), described as a `schema:WebPage` and linked to a `/page/<Title>` URI.
- **Infobox templates → RDF triples** (properties in `tg:` vocabulary; values can be literals and/or links to other resources).
- **Wiki links across pages → RDF links between entities** (in the `pages_infoboxes` data, many fields become `URIRef` objects pointing to other `/resource/` URIs).
- **Multilingual labels** (`rdfs:label` with language tags whenever available).
- **Schema validation** via SHACL shapes (loaded into a separate graph).
- **External linking**:
  - to Wikipedia pages from TG via MediaWiki API (`schema:sameAs`)
  - alignments to DBpedia / YAGO-style sources via `owl:sameAs` (based on shared Wikipedia targets)

---

## 2) Vocabulary & Shapes

### Vocabulary
We define a lightweight vocabulary aligned with **schema.org**:
- `tg:` classes are defined as `rdfs:Class` and connected using `rdfs:subClassOf` to schema.org types (e.g., `tg:Character rdfs:subClassOf schema:Person`).
- `tg:` properties are `rdf:Property`, with labels/comments and (where relevant) domain/range hints.

**File:** `kg/tg_vocab.ttl`  
**Loaded graph:** `<http://localhost:8000/graph/vocab>`

### SHACL Shapes
We translate selected infobox templates into SHACL NodeShapes that constrain:
- required types
- expected properties
- basic cardinalities / datatypes (when possible)

Each class in the vocabulary is targeted by **at least one shape**.

**File:** `kg/tg_shapes.ttl`  
**Loaded graph:** `<http://localhost:8000/graph/shapes>`

Validation report is generated and can be loaded as:
**File:** `kg/shacl_report.ttl`  
**Loaded graph:** `<http://localhost:8000/graph/shacl_report>`

---

## 3) Project requirements — checklist & justification

### ✅ The KG must capture the wiki’s content as much as possible
- We ingest a large set of pages and generate RDF for each.
- Infobox extraction yields a large triple volume (`pages_infoboxes` graph is the main one).

### ✅ Every page should correspond to an entity in the KG
- Each wiki title maps to a stable resource URI:
  - `http://localhost:8000/resource/<Title>`
  - page URI: `http://localhost:8000/page/<Title>`

### ✅ Infoboxes on wiki pages should translate into RDF triples
- Infobox fields become `tg:` properties and (when parsed as internal links) point to other resources.

### ✅ If a link exists across wiki pages, there should be an RDF triple
- Many infobox fields generate actual cross-page links as URIs (e.g., affiliation, location, house, etc.).

### ✅ KG entities must have labels in multiple languages (wherever possible)
- Resources include `rdfs:label` with many language tags whenever present in the source extraction.

### ✅ KG should be validated against schemas derived from wiki templates
- SHACL NodeShapes derived from templates are loaded and validation is executed (conforms expected).

### ✅ Vocabulary must be consistent and reuse schema.org or DBpedia ontology (but not both)
- This project reuses **schema.org** as the external reference ontology and aligns `tg:` classes to it.
- We do **not** mix with DBpedia ontology terms as the base vocabulary.

### ✅ KG should have links to other Web pages (original wiki & other KGs)
- Links to Wikipedia via `schema:sameAs` in `<graph/wikipedia_links>`.
- Alignments to DBpedia resources using `owl:sameAs` in `<graph/alignments>`.
- TG pages remain accessible via `/page/` URLs.

### ✅ KG should be accessible through a SPARQL endpoint
- Fuseki dataset exposes SPARQL query + update endpoints.

### ✅ SPARQL answers should include implicit facts
- We model class hierarchy using `rdfs:subClassOf` (e.g. `tg:Character ⊑ schema:Person`).
- When reasoning is enabled (Fuseki inference / rules), queries can return implicit types.

### ✅ Each entity/class/property must be accessible through a Linked Data interface
- A Flask web app serves:
  - `/resource/<id>` (entity description)
  - `/vocab/<term>` (class/property)
  - supports content negotiation: Turtle or HTML
- The interface can be SPARQL-backed (DESCRIBE/CONSTRUCT) so the page view reflects what is in the KG.

---

## 4) Repository structure (relevant)

- `src/tolkienkg/` — Python package with build scripts (ETL)
- `kg/` — generated TTL outputs (data products)
- `scripts/` — helper scripts to reset/load graphs into Fuseki
- `app.py` — Linked Data interface (Flask)

---

## 5) Setup

### 5.1 Python environment
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5.2 Start Fuseki

Run Fuseki :
```bash
./scripts/start_fuseki.sh
```

Verify :
```
http://localhost:3030/#/dataset/tolkien/query
```

### 5.3 Start Linked Data Interface
Run `app.py` :
```bash
./scripts/start_resolver.sh
```

Verify : 
```bash
http://127.0.0.1:8000/
```