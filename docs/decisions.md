# TolkienKG – Technical Decisions (Stage 0)

## Base vocab
We reuse **schema.org** as the main vocabulary (requirement: reuse schema.org OR DBpedia ontology, not both).
We add a small custom namespace `tg:` only when schema.org does not provide a good fit.

## Base URIs and resource vs page
We follow the DBpedia/YAGO pattern: a wiki page (document) is distinct from the described entity.

Base URI (dev default):
- BASE_URI = http://localhost:8000

Two URI spaces:
- Document pages:   http://localhost:8000/page/{slug}
- Entities (KG):    http://localhost:8000/resource/{slug}

A document is linked to its entity using:
- `schema:about` (page -> entity)

Example:
- </page/Elrond> a schema:WebPage ; schema:about </resource/Elrond> .

## Labels and languages
We store human-readable names with language tags wherever possible:
- `rdfs:label "Elrond"@en`, `rdfs:label "Elrond"@fr`, etc.

(Optionally we may also use `schema:name` with language tags, but `rdfs:label` is the baseline.)

## Links between wiki pages
If a wiki page links to another page, we create an RDF relation between the corresponding entities.
- When link semantics is unknown, we use a generic relation (custom `tg:wikiLink`) and align it with `schema:relatedTo`.

## Politeness policy for MediaWiki API
All HTTP requests must include:
- A clear User-Agent identifying the project
- Rate limiting / throttling to avoid bans
We prefer using a MediaWiki client library when practical.