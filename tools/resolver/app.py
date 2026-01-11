from __future__ import annotations

import html
import urllib.parse
from typing import Any

import requests
from flask import Flask, Response, request

FUSEKI_SPARQL = "http://localhost:3030/tolkien/sparql"
BASE = "http://localhost:8000"

app = Flask(__name__)


def slugify(title: str) -> str:
    # Keep consistent with the KG IRIs: spaces -> "_", then URL-encode
    return urllib.parse.quote(title.replace(" ", "_"), safe="")


def iri_resource(title: str) -> str:
    return f"{BASE}/resource/{slugify(title)}"


def iri_page(title: str) -> str:
    return f"{BASE}/page/{slugify(title)}"


def iri_card(card_id: str) -> str:
    # card_id is already an identifier; still URL-encode for safety
    return f"{BASE}/card/{urllib.parse.quote(card_id, safe='')}"


def tg_url(title: str) -> str:
    return "https://tolkiengateway.net/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe="")


def sparql_construct_resource_and_page(resource_iri: str, page_iri: str, limit: int = 600) -> str:
    # Pull: outgoing triples of resource, incoming triples pointing to resource, and page triples
    return f"""
PREFIX schema: <https://schema.org/>
CONSTRUCT {{
  <{resource_iri}> ?p ?o .
  ?s ?p2 <{resource_iri}> .
  <{page_iri}> ?pp ?po .
}}
WHERE {{
  {{
    GRAPH ?g {{ <{resource_iri}> ?p ?o . }}
  }} UNION {{
    GRAPH ?g {{ ?s ?p2 <{resource_iri}> . }}
  }} UNION {{
    GRAPH ?g {{ <{page_iri}> ?pp ?po . }}
  }}
}}
LIMIT {limit}
""".strip()


def sparql_construct_card(card_iri: str, limit: int = 600) -> str:
    # Pull card triples + incoming references to card
    return f"""
CONSTRUCT {{
  <{card_iri}> ?p ?o .
  ?s ?p2 <{card_iri}> .
}}
WHERE {{
  {{
    GRAPH ?g {{ <{card_iri}> ?p ?o . }}
  }} UNION {{
    GRAPH ?g {{ ?s ?p2 <{card_iri}> . }}
  }}
}}
LIMIT {limit}
""".strip()


def fetch_turtle(query: str) -> str:
    r = requests.get(
        FUSEKI_SPARQL,
        params={"query": query},
        headers={"Accept": "text/turtle"},
        timeout=30,
    )
    r.raise_for_status()
    return r.text


def fetch_json(query: str) -> dict:
    r = requests.get(
        FUSEKI_SPARQL,
        params={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def sparql_select_cards_about(resource_iri: str, lang: str = "en", limit: int = 50) -> str:
    # List cards that are schema:about the given resource, with labels/descriptions in a preferred language
    return f"""
PREFIX schema: <https://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?card ?label ?desc WHERE {{
  GRAPH ?g {{
    ?card schema:about <{resource_iri}> .
    OPTIONAL {{
      ?card rdfs:label ?label .
      FILTER(LANGMATCHES(LANG(?label), "{lang}"))
    }}
    OPTIONAL {{
      ?card schema:description ?desc .
      FILTER(LANGMATCHES(LANG(?desc), "{lang}"))
    }}
  }}
}}
LIMIT {limit}
""".strip()


def parse_cards(bindings: list[dict]) -> list[dict]:
    cards: list[dict] = []
    for b in bindings:
        card = b.get("card", {}).get("value")
        if not card:
            continue
        label = b.get("label", {}).get("value", "")
        desc = b.get("desc", {}).get("value", "")
        cards.append({"card": card, "label": label, "desc": desc})
    return cards


def render_html(
    title: str,
    kind: str,
    iri: str,
    page_iri: str,
    turtle: str,
    cards: list[dict] | None = None,
) -> str:
    cards_html = ""
    if cards:
        items = []
        for c in cards:
            card_iri = c.get("card", "")
            label = c.get("label") or card_iri
            desc = c.get("desc") or ""

            # If card IRI is in our BASE namespace, link to local /card/<id>
            link = card_iri
            if card_iri.startswith(BASE + "/card/"):
                link = "/card/" + card_iri.split("/card/", 1)[1]

            desc_short = desc[:300] + ("…" if len(desc) > 300 else "")
            items.append(
                f"<li>"
                f"<a href='{html.escape(link)}'>{html.escape(label)}</a>"
                f"<br/><small>{html.escape(desc_short)}</small>"
                f"</li>"
            )
        cards_html = "<h2>Related cards</h2><ul>" + "\n".join(items) + "</ul>"

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>{html.escape(kind)}: {html.escape(title)}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; }}
    code, pre {{ background: #f6f8fa; padding: 1rem; border-radius: 8px; overflow-x: auto; }}
    .meta a {{ margin-right: 1rem; }}
    ul {{ line-height: 1.35; }}
  </style>
</head>
<body>
  <h1>{html.escape(kind)}: {html.escape(title)}</h1>

  <div class="meta">
    <p><b>IRI resource</b>: <a href="{html.escape(iri)}">{html.escape(iri)}</a></p>
    <p><b>IRI page</b>: <a href="{html.escape(page_iri)}">{html.escape(page_iri)}</a></p>
    <p><b>TolkienGateway</b>: <a href="{html.escape(tg_url(title))}">{html.escape(tg_url(title))}</a></p>
    <p><b>Fuseki query UI</b>: <a href="http://localhost:3030/#/dataset/tolkien/query">open</a></p>
  </div>

  {cards_html}

  <h2>Triples (Turtle)</h2>
  <pre><code>{html.escape(turtle)}</code></pre>
</body>
</html>
"""

@app.get("/resource/<path:title>")
def show_resource(title: str):
    title_decoded = urllib.parse.unquote(title).replace("_", " ")
    riri = iri_resource(title_decoded)
    piri = iri_page(title_decoded)

    q = sparql_construct_resource_and_page(riri, piri)
    turtle = fetch_turtle(q)

    # Fetch related cards (best-effort)
    cards_q = sparql_select_cards_about(riri, lang="en", limit=30)
    cards_json = fetch_json(cards_q)
    cards = parse_cards(cards_json.get("results", {}).get("bindings", []))

    accept = request.headers.get("Accept", "")
    if "text/turtle" in accept:
        return Response(turtle, mimetype="text/turtle")

    return Response(render_html(title_decoded, "Resource", riri, piri, turtle, cards=cards), mimetype="text/html")


@app.get("/page/<path:title>")
def show_page(title: str):
    title_decoded = urllib.parse.unquote(title).replace("_", " ")
    piri = iri_page(title_decoded)
    riri = iri_resource(title_decoded)

    q = sparql_construct_resource_and_page(riri, piri)
    turtle = fetch_turtle(q)

    accept = request.headers.get("Accept", "")
    if "text/turtle" in accept:
        return Response(turtle, mimetype="text/turtle")

    return Response(render_html(title_decoded, "Page", riri, piri, turtle), mimetype="text/html")


@app.get("/card/<path:card_id>")
def show_card(card_id: str):
    card_id_decoded = urllib.parse.unquote(card_id)
    ciri = iri_card(card_id_decoded)

    q = sparql_construct_card(ciri)
    turtle = fetch_turtle(q)

    accept = request.headers.get("Accept", "")
    if "text/turtle" in accept:
        return Response(turtle, mimetype="text/turtle")

    # For cards, we don't really have a "page", but reuse layout
    return Response(render_html(card_id_decoded, "Card", ciri, ciri, turtle), mimetype="text/html")


@app.get("/")
def index():
    return Response(
        "<h1>Tolkien_KG Resolver</h1>"
        "<p>Try:</p>"
        "<ul>"
        "<li><a href='/resource/Sauron'>/resource/Sauron</a></li>"
        "<li><a href='/page/Sauron'>/page/Sauron</a></li>"
        "</ul>",
        mimetype="text/html",
    )

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)