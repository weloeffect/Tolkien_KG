from __future__ import annotations

import html
import json
import os
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import requests
from flask import Flask, Response, redirect, request, url_for

from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL, XSD, Namespace

# -----------------------------
# Config
# -----------------------------
BASE = os.getenv("LD_BASE", "http://localhost:8000")
FUSEKI_SPARQL = os.getenv("FUSEKI_SPARQL", "http://localhost:3030/tolkien/sparql")

# Tolkien Gateway MediaWiki API (para resolver arquivos de imagem -> URL direto)
TG_API = os.getenv("TG_API", "https://tolkiengateway.net/w/api.php")

# Cache simples para resolver imagens (evita bater na API toda hora)
CACHE_DIR = Path(os.getenv("LD_CACHE_DIR", "cache/ld_interface"))
IMG_CACHE = CACHE_DIR / "imageinfo"
IMG_CACHE.mkdir(parents=True, exist_ok=True)

# Namespaces úteis
SCHEMA = Namespace("https://schema.org/")
TG = Namespace(f"{BASE}/vocab/")
RES = Namespace(f"{BASE}/resource/")
VOC = Namespace(f"{BASE}/vocab/")
CARD = Namespace(f"{BASE}/card/")

# Pra “pretty print” de URIs (estilo DBpedia)
PREFIXES = {
    str(RDF): "rdf",
    str(RDFS): "rdfs",
    str(OWL): "owl",
    str(XSD): "xsd",
    str(SCHEMA): "schema",
    str(TG): "tg",
    str(RES): "res",
    str(VOC): "tg",  # também tg (vocab)
    str(CARD): "card",
}

app = Flask(__name__)


# -----------------------------
# Helpers: SPARQL
# -----------------------------
def sparql_query(query: str, accept: str = "text/turtle", timeout: int = 60) -> bytes:
    """
    Usa POST (mais robusto que GET) para evitar 400 por URL grande/limites do Jetty/Fuseki.
    """
    q = (query or "").strip()

    r = requests.post(
        FUSEKI_SPARQL,
        data={"query": q},
        headers={"Accept": accept},
        timeout=timeout,
    )

    if not r.ok:
        snippet = (r.text or "")[:800]
        raise RuntimeError(f"Fuseki SPARQL error {r.status_code}: {snippet}")

    return r.content


def describe_ttl(iri: str) -> bytes:
    q = f"DESCRIBE <{iri}>"
    return sparql_query(q, accept="text/turtle")


# -----------------------------
# Helpers: content negotiation
# -----------------------------
def wants_html() -> bool:
    fmt = (request.args.get("format") or "").lower().strip()
    if fmt in ("html", "page"):
        return True
    if fmt in ("ttl", "turtle", "rdf", "jsonld", "ntriples"):
        return False

    accept = (request.headers.get("Accept") or "").lower()
    # se o browser pedir HTML explicitamente, prioriza HTML
    if "text/html" in accept or "application/xhtml+xml" in accept:
        return True
    return False


def negotiated_rdf_mimetype() -> str:
    fmt = (request.args.get("format") or "").lower().strip()
    if fmt in ("ttl", "turtle"):
        return "text/turtle"
    if fmt in ("jsonld", "json-ld"):
        return "application/ld+json"
    if fmt in ("nt", "ntriples"):
        return "application/n-triples"

    accept = (request.headers.get("Accept") or "").lower()
    if "application/ld+json" in accept:
        return "application/ld+json"
    if "application/n-triples" in accept:
        return "application/n-triples"
    return "text/turtle"


# -----------------------------
# Helpers: URI formatting
# -----------------------------
def qname_or_uri(u: str) -> str:
    for ns, pfx in PREFIXES.items():
        if u.startswith(ns):
            local = u[len(ns) :]
            return f"{pfx}:{local}"
    return u


def is_uri(s: Any) -> bool:
    return isinstance(s, (URIRef,)) or (isinstance(s, str) and (s.startswith("http://") or s.startswith("https://")))


def escape(s: str) -> str:
    return html.escape(s, quote=True)


def preferred_lang() -> str:
    # tenta pegar algo como "fr", "en", "pt-BR"
    al = request.headers.get("Accept-Language", "")
    if not al:
        return "en"
    # pega o primeiro token antes de ; ou ,
    first = al.split(",")[0].strip()
    return first or "en"


def best_label(g: Graph, subj: URIRef, lang: str) -> Optional[str]:
    labels = list(g.objects(subj, RDFS.label))
    if not labels:
        return None

    # 1) match exato do idioma (pt-BR etc)
    for l in labels:
        if isinstance(l, Literal) and (l.language or "").lower() == lang.lower():
            return str(l)

    # 2) match por prefixo (pt-BR -> pt)
    if "-" in lang:
        base = lang.split("-", 1)[0].lower()
        for l in labels:
            if isinstance(l, Literal) and (l.language or "").lower() == base:
                return str(l)

    # 3) inglês
    for l in labels:
        if isinstance(l, Literal) and (l.language or "").lower() == "en":
            return str(l)

    # 4) qualquer literal
    for l in labels:
        if isinstance(l, Literal):
            return str(l)

    return str(labels[0])


# -----------------------------
# Image resolution (TG file -> direct URL)
# -----------------------------
def _img_cache_path(filename: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename)[:180]
    return IMG_CACHE / f"{safe}.json"


def resolve_tg_file_to_url(filename: str, timeout: int = 25) -> Optional[str]:
    """
    Recebe algo tipo: "Tatyafinwe - Portrait of Elrond.jpg"
    e tenta obter URL direta via MediaWiki API (imageinfo).
    """
    if not filename or not isinstance(filename, str):
        return None

    # normaliza: remove possíveis "File:" e trims
    name = filename.strip()
    name = name.replace("File:", "").replace("file:", "").strip()
    if not name:
        return None

    cache_p = _img_cache_path(name)
    if cache_p.exists():
        try:
            cached = json.loads(cache_p.read_text(encoding="utf-8"))
            return cached.get("url")
        except Exception:
            pass

    title = f"File:{name}"
    params = {
        "action": "query",
        "titles": title,
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json",
        "redirects": 1,
    }
    try:
        r = requests.get(TG_API, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None

    url = None
    try:
        pages = (data.get("query") or {}).get("pages") or {}
        for _, page in pages.items():
            ii = page.get("imageinfo")
            if isinstance(ii, list) and ii:
                url = ii[0].get("url")
                break
    except Exception:
        url = None

    try:
        cache_p.write_text(json.dumps({"url": url}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    return url


def pick_image_url(g: Graph, subj: URIRef) -> Optional[str]:
    # 1) schema:image (se já vier como URL)
    for o in g.objects(subj, SCHEMA.image):
        if isinstance(o, URIRef):
            return str(o)
        if isinstance(o, Literal):
            s = str(o).strip()
            if s.startswith("http://") or s.startswith("https://"):
                return s

    # 2) tg:image normalmente vem literal com nome do arquivo
    for o in g.objects(subj, TG.image):
        if isinstance(o, Literal):
            filename = str(o).strip()
            u = resolve_tg_file_to_url(filename)
            if u:
                return u

    return None


# -----------------------------
# HTML rendering (DBpedia-like)
# -----------------------------
@dataclass
class Row:
    p: str
    o_html: str


def object_to_html(o: Any) -> str:
    if isinstance(o, URIRef):
        u = str(o)
        # se for do nosso domínio, linka para nossa interface
        if u.startswith(f"{BASE}/resource/") or u.startswith(f"{BASE}/vocab/") or u.startswith(f"{BASE}/card/"):
            return f'<a href="{escape(u)}">{escape(qname_or_uri(u))}</a>'
        # externo
        return f'<a href="{escape(u)}" target="_blank" rel="noopener">{escape(qname_or_uri(u))}</a>'

    if isinstance(o, Literal):
        txt = escape(str(o))
        if o.language:
            return f"{txt} <span class='lang'>@{escape(o.language)}</span>"
        if o.datatype:
            return f"{txt} <span class='dtype'>^^{escape(qname_or_uri(str(o.datatype)))}</span>"
        return txt

    return escape(str(o))


def build_property_rows(g: Graph, subj: URIRef) -> list[Row]:
    # agrupa por predicado e limita um pouco pra não explodir HTML
    preds = sorted({p for p in g.predicates(subj, None)}, key=lambda x: str(x))
    rows: list[Row] = []

    for p in preds:
        p_str = str(p)

        # escondemos alguns "ruins" de debug se quiser (opcional)
        # if p == RDF.type: continue

        objs = list(g.objects(subj, p))
        # DBpedia-like: várias linhas para mesmo predicado
        for o in objs[:200]:
            rows.append(Row(p=qname_or_uri(p_str), o_html=object_to_html(o)))

        if len(objs) > 200:
            rows.append(Row(p=qname_or_uri(p_str), o_html=f"<em>... (+{len(objs)-200} more)</em>"))

    return rows


def html_page(title: str, iri: str, ttl_bytes: bytes) -> str:
    lang = preferred_lang()

    g = Graph()
    g.parse(data=ttl_bytes.decode("utf-8", errors="replace"), format="turtle")

    subj = URIRef(iri)

    label = best_label(g, subj, lang) or iri.rsplit("/", 1)[-1]
    img_url = pick_image_url(g, subj)

    types = sorted({str(o) for o in g.objects(subj, RDF.type)})
    same_as = sorted({str(o) for o in g.objects(subj, OWL.sameAs)} | {str(o) for o in g.objects(subj, SCHEMA.sameAs)})

    rows = build_property_rows(g, subj)

    # Link para RDF
    ttl_link = f"{iri}?format=ttl"
    jsonld_link = f"{iri}?format=jsonld"
    nt_link = f"{iri}?format=nt"

    # CSS “DBpedia-ish” simples
    css = """
    body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin:0; background:#f7f7f7; color:#111; }
    header { background:#1f4e79; color:white; padding:14px 18px; }
    header a { color:#dbe9ff; text-decoration:none; }
    .wrap { max-width: 1180px; margin: 18px auto; padding: 0 14px; }
    .grid { display:flex; gap:18px; align-items:flex-start; }
    .main { flex: 1 1 720px; background:white; border:1px solid #ddd; border-radius:10px; padding:16px; }
    .side { flex: 0 0 360px; background:white; border:1px solid #ddd; border-radius:10px; padding:16px; }
    h1 { font-size: 26px; margin: 0 0 8px 0; }
    .iri { color:#444; font-size: 13px; overflow-wrap:anywhere; }
    .btns a { display:inline-block; margin:10px 10px 0 0; padding:6px 10px; border:1px solid #1f4e79; border-radius:8px; text-decoration:none; color:#1f4e79; font-size: 13px; }
    .btns a:hover { background:#eaf2ff; }
    .infobox img { max-width:100%; border-radius:8px; border:1px solid #ddd; background:#fff; }
    table { width:100%; border-collapse: collapse; margin-top:10px; }
    th, td { text-align:left; border-top:1px solid #eee; padding:8px 8px; vertical-align: top; }
    th { width: 32%; color:#333; font-weight:600; }
    .pill { display:inline-block; padding:2px 8px; border-radius:999px; background:#eef4ff; border:1px solid #d7e6ff; margin: 2px 6px 2px 0; font-size: 12px; }
    .lang, .dtype { color:#666; font-size:12px; margin-left: 6px; }
    .sec-title { font-size: 14px; font-weight:700; margin-top: 12px; margin-bottom: 6px; color:#333; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
    footer { color:#666; font-size: 12px; padding: 10px 0 25px 0; }
    """

    # HTML
    type_html = " ".join(
        f'<span class="pill">{escape(qname_or_uri(t))}</span>' for t in types[:30]
    ) + (f"<em> ... (+{len(types)-30})</em>" if len(types) > 30 else "")

    sameas_html = ""
    if same_as:
        sameas_html = "<ul>" + "".join(
            f'<li><a href="{escape(u)}" target="_blank" rel="noopener">{escape(u)}</a></li>'
            for u in same_as[:50]
        ) + ("<li><em>... more</em></li>" if len(same_as) > 50 else "") + "</ul>"

    props_html = "\n".join(
        f"<tr><th>{escape(r.p)}</th><td>{r.o_html}</td></tr>" for r in rows
    ) or "<tr><td><em>No triples returned by DESCRIBE.</em></td></tr>"

    img_html = ""
    if img_url:
        img_html = f"""
        <div class="infobox">
          <img src="{escape(img_url)}" alt="{escape(label)}" loading="lazy"/>
        </div>
        """

    return f"""<!doctype html>
<html lang="{escape(lang)}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{escape(label)} — Tolkien KG</title>
  <style>{css}</style>
</head>
<body>
<header>
  <div class="wrap">
    <div style="display:flex; justify-content:space-between; gap:14px; align-items:center;">
      <div><strong>Tolkien KG</strong> <span style="opacity:.85">/ Linked Data interface</span></div>
      <div>
        <a href="{escape('http://localhost:3030/#/dataset/tolkien/query')}" target="_blank" rel="noopener">Fuseki</a>
        <span style="opacity:.6"> • </span>
        <a href="{escape(BASE)}">Home</a>
      </div>
    </div>
  </div>
</header>

<div class="wrap">
  <div class="grid">
    <div class="main">
      <h1>{escape(label)}</h1>
      <div class="iri mono">{escape(iri)}</div>

      <div class="btns">
        <a href="{escape(ttl_link)}">Turtle</a>
        <a href="{escape(jsonld_link)}">JSON-LD</a>
        <a href="{escape(nt_link)}">N-Triples</a>
      </div>

      <div class="sec-title">Types</div>
      <div>{type_html or "<em>(none)</em>"}</div>

      <div class="sec-title">Properties</div>
      <table>
        <tbody>
          {props_html}
        </tbody>
      </table>

      <footer>
        Data source: Fuseki DESCRIBE (may include inferred facts depending on your dataset config).
      </footer>
    </div>

    <div class="side">
      {img_html}

      <div class="sec-title">SameAs links</div>
      {sameas_html if same_as else "<em>No owl:sameAs / schema:sameAs found.</em>"}

      <div class="sec-title">SPARQL</div>
      <div style="font-size:13px;">
        Endpoint: <span class="mono">{escape(FUSEKI_SPARQL)}</span><br/>
        Example: <span class="mono">DESCRIBE &lt;{escape(iri)}&gt;</span>
      </div>
    </div>
  </div>
</div>

</body>
</html>
"""


# -----------------------------
# Routes
# -----------------------------
def resource_iri_from_path(path: str) -> str:
    # path já vem “decoded” pelo Flask; precisamos re-encode seguro
    # porque seu KG usa URIs com %XX (ex: Elw%C3%AB)
    encoded = urllib.parse.quote(path, safe=":/()%#?&=+,-._~")
    # mas não queremos escapar "/" dentro do slug (você usa / em alguns resources)
    encoded = encoded.replace("%2F", "/")
    return f"{BASE}/resource/{encoded}"


def vocab_iri_from_path(path: str) -> str:
    encoded = urllib.parse.quote(path, safe=":/()%#?&=+,-._~")
    encoded = encoded.replace("%2F", "/")
    return f"{BASE}/vocab/{encoded}"

def card_iri_from_path(path: str) -> str:
    encoded = urllib.parse.quote(path, safe=":/()%#?&=+,-._~")
    encoded = encoded.replace("%2F", "/")
    return f"{BASE}/card/{encoded}"


@app.route("/")
def home() -> Response:
    html_home = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Tolkien KG</title>
  <style>
    body {{ font-family:system-ui; padding:18px; max-width: 900px; margin: 0 auto; }}
    input[type=text] {{ width: 100%; padding: 10px; font-size: 16px; }}
    button {{ padding: 10px 14px; font-size: 16px; margin-top: 10px; }}
    .hint {{ color:#666; font-size: 13px; margin-top: 6px; }}
  </style>
</head>
<body>
  <h2>Tolkien KG — Linked Data</h2>

  <form action="/search" method="get">
    <input type="text" name="q" placeholder="Search by label (e.g., Elrond, Gandalf, Rivendell)"/>
    <button type="submit">Search</button>
    <div class="hint">Tip: add &lang=en (or fr, pt-BR...) to prioritize a language.</div>
  </form>

  <hr/>

  <ul>
    <li>SPARQL endpoint: <code>{html.escape(FUSEKI_SPARQL)}</code></li>
    <li>Example resource: <a href="{BASE}/resource/Elrond">{BASE}/resource/Elrond</a></li>
    <li>Example card: <a href="{BASE}/card/WH-4">{BASE}/card/WH-4</a></li>
    <li>Vocabulary: <a href="{BASE}/vocab/Character">{BASE}/vocab/Character</a></li>
  </ul>
</body>
</html>"""
    return Response(html_home, content_type="text/html; charset=utf-8")

@app.route("/resource/<path:rid>")
def resource(rid: str) -> Response:
    iri = resource_iri_from_path(rid)

    if wants_html():
        ttl = describe_ttl(iri)
        return Response(html_page("resource", iri, ttl), content_type="text/html; charset=utf-8")

    # RDF
    mime = negotiated_rdf_mimetype()
    q = f"DESCRIBE <{iri}>"
    data = sparql_query(q, accept=mime)
    return Response(data, content_type=f"{mime}; charset=utf-8")


@app.route("/vocab/<path:term>")
def vocab(term: str) -> Response:
    iri = vocab_iri_from_path(term)

    if wants_html():
        ttl = describe_ttl(iri)
        return Response(html_page("vocab", iri, ttl), content_type="text/html; charset=utf-8")

    mime = negotiated_rdf_mimetype()
    q = f"DESCRIBE <{iri}>"
    data = sparql_query(q, accept=mime)
    return Response(data, content_type=f"{mime}; charset=utf-8")


@app.route("/sparql")
def sparql_redirect() -> Response:
    return redirect(FUSEKI_SPARQL.replace("/sparql", ""), code=302)


@app.get("/card/<path:cid>")
def card(cid: str) -> Response:
    iri = card_iri_from_path(cid)

    if wants_html():
        ttl = describe_ttl(iri)
        return Response(html_page("card", iri, ttl), content_type="text/html; charset=utf-8")

    mime = negotiated_rdf_mimetype()
    q = f"DESCRIBE <{iri}>"
    data = sparql_query(q, accept=mime)
    return Response(data, content_type=f"{mime}; charset=utf-8")

@app.route("/search")
def search() -> Response:
    q = (request.args.get("q") or "").strip()
    lang = (request.args.get("lang") or preferred_lang() or "en").strip()
    if not q:
        return redirect("/", code=302)

    # lang base p/ LANGMATCHES: "pt-BR" -> "pt"
    lang_base = lang.split(",", 1)[0].split(";", 1)[0].strip()
    lang_base = lang_base.split("-", 1)[0].strip().lower() or "en"

    # escape simples de aspas
    q_esc = q.replace("\\", "\\\\").replace('"', '\\"')

    # restringe aos teus grafos principais (evita “buscar em tudo” e reduz ruído)
    # ajuste a lista se quiser incluir/remover grafos
    graphs = [
        f"{BASE}/graph/pages_infoboxes",
        f"{BASE}/graph/backbone",
        f"{BASE}/graph/vocab",
        f"{BASE}/graph/cards",
        f"{BASE}/graph/main",
        f"{BASE}/graph/lotrwiki",
    ]
    values_graphs = " ".join(f"<{g}>" for g in graphs)

    sparql = f"""
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?s (SAMPLE(?label) AS ?labelPick) (MAX(?score0) AS ?score)
WHERE {{
  VALUES ?g {{ {values_graphs} }}
  GRAPH ?g {{
    ?s rdfs:label ?label .
    FILTER(isLiteral(?label))
    FILTER(CONTAINS(LCASE(STR(?label)), LCASE("{q_esc}")))

    BIND(
      IF(LANGMATCHES(LANG(?label), "{lang_base}"), 3,
        IF(LANGMATCHES(LANG(?label), "en"), 2,
          IF(LANG(?label) = "", 1, 0)
        )
      ) AS ?score0
    )
  }}
}}
GROUP BY ?s
ORDER BY DESC(?score) LCASE(STR(?labelPick))
LIMIT 80
"""

    data = sparql_query(sparql, accept="application/sparql-results+json")
    js = json.loads(data.decode("utf-8", errors="replace"))

    rows = []
    for b in js.get("results", {}).get("bindings", []):
        s = b["s"]["value"]
        label = b.get("labelPick", {}).get("value", s.rsplit("/", 1)[-1])
        rows.append((s, label))

    items_html = "".join(
        f'<li><a href="{escape(s)}">{escape(label)}</a> '
        f'<span style="color:#666;font-size:12px;">({escape(s)})</span></li>'
        for s, label in rows
    ) or "<li><em>No results.</em></li>"

    html_out = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Search — Tolkien KG</title>
  <style>
    body {{ font-family:system-ui; padding:18px; max-width: 1100px; margin:0 auto; }}
    input[type=text] {{ width: 100%; padding: 10px; font-size: 16px; }}
    button {{ padding: 10px 14px; font-size: 16px; margin-top: 10px; }}
    .meta {{ color:#666; font-size: 13px; margin-top:6px; }}
    ul {{ line-height: 1.45; }}
  </style>
</head>
<body>
  <h2>Search</h2>
  <form action="/search" method="get">
    <input type="text" name="q" value="{escape(q)}" />
    <input type="hidden" name="lang" value="{escape(lang)}"/>
    <button type="submit">Search</button>
    <div class="meta">Language priority: <code>{escape(lang_base)}</code> → <code>en</code> → any</div>
  </form>

  <hr/>
  <p><strong>Results</strong> for <code>{escape(q)}</code>:</p>
  <ul>
    {items_html}
  </ul>

  <p><a href="/">Back to home</a></p>
</body>
</html>"""

    return Response(html_out, content_type="text/html; charset=utf-8")

if __name__ == "__main__":
    # http://localhost:8000
    app.run(host="0.0.0.0", port=8000, debug=True)