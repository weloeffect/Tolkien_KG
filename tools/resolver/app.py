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
    return urllib.parse.quote(title.replace(" ", "_"), safe="")

def iri_resource(title: str) -> str:
    return f"{BASE}/resource/{slugify(title)}"

def iri_page(title: str) -> str:
    return f"{BASE}/page/{slugify(title)}"

def tg_url(title: str) -> str:
    return "https://tolkiengateway.net/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe="")

def sparql_construct(iri: str, page_iri: str, limit: int = 400) -> str:
    return f"""
PREFIX schema: <https://schema.org/>
CONSTRUCT {{
  <{iri}> ?p ?o .
  ?s ?p2 <{iri}> .
  <{page_iri}> ?pp ?po .
}}
WHERE {{
  {{
    GRAPH ?g {{ <{iri}> ?p ?o . }}
  }} UNION {{
    GRAPH ?g {{ ?s ?p2 <{iri}> . }}
  }} UNION {{
    GRAPH ?g {{ <{page_iri}> ?pp ?po . }}
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

def render_html(title: str, kind: str, iri: str, page_iri: str, turtle: str) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>{html.escape(kind)}: {html.escape(title)}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; }}
    code, pre {{ background: #f6f8fa; padding: 1rem; border-radius: 8px; overflow-x: auto; }}
    .meta a {{ margin-right: 1rem; }}
  </style>
</head>
<body>
  <h1>{html.escape(kind)}: {html.escape(title)}</h1>

  <div class="meta">
    <p><b>IRI resource</b>: <a href="{iri}">{iri}</a></p>
    <p><b>IRI page</b>: <a href="{page_iri}">{page_iri}</a></p>
    <p><b>TolkienGateway</b>: <a href="{tg_url(title)}">{tg_url(title)}</a></p>
    <p><b>Fuseki query UI</b>: <a href="http://localhost:3030/#/dataset/tolkien/query">open</a></p>
  </div>

  <h2>Triples (Turtle)</h2>
  <pre><code>{html.escape(turtle)}</code></pre>
</body>
</html>
"""

@app.get("/resource/<path:title>")
def show_resource(title: str):
    title_decoded = urllib.parse.unquote(title).replace("_", " ")
    iri = iri_resource(title_decoded)
    piri = iri_page(title_decoded)

    q = sparql_construct(iri, piri)
    turtle = fetch_turtle(q)

    accept = request.headers.get("Accept", "")
    if "text/turtle" in accept:
        return Response(turtle, mimetype="text/turtle")

    return Response(render_html(title_decoded, "Resource", iri, piri, turtle), mimetype="text/html")

@app.get("/page/<path:title>")
def show_page(title: str):
    title_decoded = urllib.parse.unquote(title).replace("_", " ")
    iri = iri_page(title_decoded)
    riri = iri_resource(title_decoded)

    q = sparql_construct(riri, iri)
    turtle = fetch_turtle(q)

    accept = request.headers.get("Accept", "")
    if "text/turtle" in accept:
        return Response(turtle, mimetype="text/turtle")

    return Response(render_html(title_decoded, "Page", riri, iri, turtle), mimetype="text/html")

@app.get("/")
def index():
    return Response(
        "<h1>Tolkien_KG Resolver</h1><p>Try /resource/Sauron or /page/Sauron</p>",
        mimetype="text/html",
    )

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)