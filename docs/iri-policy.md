# IRI policy

## Slugs
We use stable, URL-safe slugs derived from page titles.
Rules:
- Trim spaces
- Replace spaces with underscores
- Keep ASCII when possible (fallback: percent-encoding if needed)
- Preserve original capitalization (default), because MediaWiki titles are case-sensitive in practice

Examples:
- "Elrond"            -> "Elrond"
- "The One Ring"      -> "The_One_Ring"
- "Minas Tirith"      -> "Minas_Tirith"

## Page vs Resource
Given a slug S:

Document (HTML/Turtle representation of the page):
- http://localhost:8000/page/S

Entity described by that page:
- http://localhost:8000/resource/S

## Page-to-entity link
We assert that each document is about one entity:

<http://localhost:8000/page/S> a schema:WebPage ;
  schema:about <http://localhost:8000/resource/S> .

## Entity typing (schema.org)
Entities are typed using schema.org where applicable.
Examples:
- Characters -> schema:Person (or schema:Person + tg:Character as needed later)
- Places -> schema:Place
- Organizations -> schema:Organization