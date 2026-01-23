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

### The KG must capture the wiki’s content as much as possible
- We ingest a large set of pages and generate RDF for each.
- Infobox extraction yields a large triple volume (`pages_infoboxes` graph is the main one).

### Every page should correspond to an entity in the KG
- Each wiki title maps to a stable resource URI:
  - `http://localhost:8000/resource/<Title>`
  - page URI: `http://localhost:8000/page/<Title>`

### Infoboxes on wiki pages should translate into RDF triples
- Infobox fields become `tg:` properties and (when parsed as internal links) point to other resources.

### If a link exists across wiki pages, there should be an RDF triple
- Many infobox fields generate actual cross-page links as URIs (e.g., affiliation, location, house, etc.).

### KG entities must have labels in multiple languages (wherever possible)
- Resources include `rdfs:label` with many language tags whenever present in the source extraction.

### KG should be validated against schemas derived from wiki templates
- SHACL NodeShapes derived from templates are loaded and validation is executed (conforms expected).

### Vocabulary must be consistent and reuse schema.org or DBpedia ontology (but not both)
- This project reuses **schema.org** as the external reference ontology and aligns `tg:` classes to it.
- We do **not** mix with DBpedia ontology terms as the base vocabulary.

### KG should have links to other Web pages (original wiki & other KGs)
- Links to Wikipedia via `schema:sameAs` in `<graph/wikipedia_links>`.
- Alignments to DBpedia resources using `owl:sameAs` in `<graph/alignments>`.
- TG pages remain accessible via `/page/` URLs.

### KG should be accessible through a SPARQL endpoint
- Fuseki dataset exposes SPARQL query + update endpoints.

### SPARQL answers should include implicit facts
- We model class hierarchy using `rdfs:subClassOf` (e.g. `tg:Character ⊑ schema:Person`).
- When reasoning is enabled (Fuseki inference / rules), queries can return implicit types.

### Each entity/class/property must be accessible through a Linked Data interface
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
- `tools/resolver/app.py` — Linked Data interface (Flask)
- `fuseki/` — Fuseki configuration and database storage
- `cache/` — Cached API responses and parsed data
- `data/` — Source data files (wikitext, cards, etc.)

---

## 5) Prerequisites

Before starting, ensure you have:

- **Python 3.8+** (check with `python --version`)
- **Java 11+** (required for Fuseki, check with `java -version`)
- **curl** (for loading scripts, usually pre-installed on Linux/Mac)

## 6) Setup

### 6.1 Python environment
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 6.2 Setup Fuseki (first time only)

Download and install Apache Jena Fuseki:
```bash
./scripts/setup_fuseki.sh
```

This will download Fuseki 5.6.0 and extract it to `tools/fuseki/`.

### 6.3 Start Fuseki

Run Fuseki:
```bash
./scripts/start_fuseki.sh
```

Verify it's running:
```bash
./scripts/smoke_test_fuseki.sh
```

Or visit in browser:
```
http://localhost:3030/#/dataset/tolkien/query
```

### 6.4 Start Linked Data Interface

Run the Flask app:
```bash
./scripts/start_resolver.sh
```

Verify:
```
http://127.0.0.1:8000/
```

---

## 7) Loading and Using the Knowledge Graph

The Knowledge Graph Turtle files are already generated and available in the `kg/` directory. Follow these steps to load them into Fuseki and start using the system.

### 7.1 Load Data into Fuseki

**Make sure Fuseki is running** (see 6.3). Then load the TTL files in this order:

```bash
# 1. Load vocabulary (defines tg: classes and properties)
./scripts/load_ttl.sh kg/tg_vocab.ttl http://localhost:8000/graph/vocab

# 2. Load SHACL shapes (for validation)
./scripts/load_ttl.sh kg/tg_shapes.ttl http://localhost:8000/graph/shapes

# 3. Load backbone (page structure)
./scripts/load_ttl.sh kg/allpages_backbone.ttl http://localhost:8000/graph/backbone

# 4. Load main infobox data
./scripts/load_ttl.sh kg/pages_infoboxes_from_parse.ttl http://localhost:8000/graph/pages_infoboxes

# 5. Load additional data 
./scripts/load_ttl.sh kg/wikipedia_links.ttl http://localhost:8000/graph/wikipedia_links
./scripts/load_ttl.sh kg/alignments.ttl http://localhost:8000/graph/alignments
./scripts/load_ttl.sh kg/lotrwiki_labels.ttl http://localhost:8000/graph/lotrwiki
./scripts/load_ttl.sh kg/cards.ttl http://localhost:8000/graph/cards
```

**Note:** If you need to reload a graph (e.g., after updating the TTL file), reset it first:
```bash
./scripts/reset_graph.sh http://localhost:8000/graph/pages_infoboxes
./scripts/load_ttl.sh kg/pages_infoboxes_from_parse.ttl http://localhost:8000/graph/pages_infoboxes
```

### 7.2 Validate with SHACL

After loading data, you can validate it against the SHACL shapes:

```bash
python scripts/validate_shacl.py
```

This will:
- Load the data graph (`kg/pages_infoboxes_from_parse.ttl`)
- Load the shapes (`kg/tg_shapes.ttl`)
- Run validation with RDFS inference
- Print the validation report
- Save the report to `kg/shacl_report.ttl`

**Expected output:** `CONFORMS: True` (or a list of validation errors if issues are found)

---

## 8) Testing the System

### 8.1 Test Fuseki SPARQL Endpoint

**Quick test:**
```bash
./scripts/smoke_test_fuseki.sh
```

**Manual test via browser:**
1. Visit: `http://localhost:3030/#/dataset/tolkien/query`
2. Try this query:
```sparql
# Count triples per graph
PREFIX tg: <http://localhost:8000/vocab/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?g (COUNT(*) AS ?count) 
WHERE { 
  GRAPH ?g { 
    ?s ?p ?o 
  } 
} 
GROUP BY ?g 
ORDER BY DESC(?count)
```

**Test via command line:**

```bash
# Count all triples across all graphs
curl -G \
  --data-urlencode 'query=SELECT (COUNT(*) AS ?count) WHERE { GRAPH ?g { ?s ?p ?o } }' \
  'http://localhost:3030/tolkien/sparql' \
  -H 'Accept: application/sparql-results+json'
```

### 8.2 Test Linked Data Interface

**Home page:**
- Visit: `http://127.0.0.1:8000/`

**Resource page (HTML):**
- Visit: `http://127.0.0.1:8000/resource/Elrond`
- Should show entity description with properties

**Resource page (RDF/Turtle):**
- Visit: `http://127.0.0.1:8000/resource/Elrond?format=ttl`
- Should return Turtle RDF

**Search:**
- Visit: `http://127.0.0.1:8000/search?q=Gandalf`
- Should return matching resources

**Vocabulary term:**
- Visit: `http://127.0.0.1:8000/vocab/Character`
- Should show class definition

### 8.3 Example SPARQL Queries

**Find all characters:**
```sparql
PREFIX tg: <http://localhost:8000/vocab/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?character ?label WHERE {
  ?character rdf:type tg:Character .
  ?character rdfs:label ?label .
  FILTER(LANG(?label) = "en")
}
LIMIT 20
```

**Find characters and their affiliations:**
```sparql
PREFIX tg: <http://localhost:8000/vocab/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?character ?label ?affiliation WHERE {
  ?character rdf:type tg:Character .
  ?character rdfs:label ?label .
  ?character tg:affiliation ?affiliation .
  FILTER(LANG(?label) = "en")
}
LIMIT 20
```

**Count triples per graph:**
```sparql
SELECT ?g (COUNT(*) AS ?count) WHERE {
  GRAPH ?g { ?s ?p ?o }
}
GROUP BY ?g
ORDER BY DESC(?count)
```

---

## 9) Optional: Rebuilding the Knowledge Graph

If you need to rebuild the Knowledge Graph from scratch (e.g., to update with new data from Tolkien Gateway), follow these steps. **Note**: The full build process can take several hours depending on the number of pages processed.

### 9.1 Build Order

#### Step 1: Build the backbone (all pages)

Creates the basic structure with all Tolkien Gateway pages as entities:

```bash
# From project root, add src to Python path:
PYTHONPATH=src python -m tolkienkg.build_all_pages_backbone
```

**Output:** `kg/allpages_backbone.ttl`

#### Step 2: Build infobox data (main ETL)

Extracts infobox templates and converts them to RDF triples. This is the most time-consuming step.

**For testing** (first 100 pages):
```bash
PYTHONPATH=src python -c "from tolkienkg.build_pages_infoboxes_from_parse import main; main(limit_pages=100)"
```

**For full build** (all pages):
```bash
PYTHONPATH=src python -m tolkienkg.build_pages_infoboxes_from_parse
```

**Output:** `kg/pages_infoboxes_from_parse.ttl`

**Note:** This script uses caching to avoid re-fetching pages. Cached data is stored in `cache/tg_parse_pages/`. The full build can take several hours depending on the number of pages.

#### Step 3: Build additional data (optional)

These scripts enhance the KG with external links and multilingual labels:

**Wikipedia links:**
```bash
PYTHONPATH=src python -m tolkienkg.build_wikipedia_links
```
**Output:** `kg/wikipedia_links.ttl`

**DBpedia alignments:**
```bash
PYTHONPATH=src python -m tolkienkg.build_alignments
```
**Output:** `kg/alignments.ttl`

**Multilingual labels:**
```bash
PYTHONPATH=src python -m tolkienkg.build_lotrwiki_labels
```
**Output:** `kg/lotrwiki_labels.ttl`

**Card game data:**
```bash
PYTHONPATH=src python -m tolkienkg.build_cards_rdf
```
**Output:** `kg/cards.ttl`

**Alternative:** If you prefer, you can run scripts directly from the `src/` directory:
```bash
cd src
python -m tolkienkg.build_all_pages_backbone
```

After rebuilding, follow the loading instructions in section 7.1 to load the new TTL files into Fuseki.
