from __future__ import annotations

import time
from urllib.parse import quote

import requests
from rdflib import Graph, URIRef
from rdflib.namespace import OWL

DBPEDIA_ENDPOINT = "https://dbpedia.org/sparql"
YAGO_ENDPOINT = "https://qlever.dev/api/yago-4"  # QLever backend URL

IN_TTL = "kg/wikipedia_links.ttl"
OUT_TTL = "kg/alignments.ttl"

HEADERS_JSON = {"Accept": "application/sparql-results+json"}

def sparql_select(endpoint: str, query: str, timeout_s: int = 30) -> list[dict]:
    r = requests.get(endpoint, params={"query": query}, headers=HEADERS_JSON, timeout=timeout_s)
    r.raise_for_status()
    return r.json()["results"]["bindings"]

def align_dbpedia(wiki_url: str) -> list[str]:
    q = f"""
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
SELECT ?s WHERE {{
  ?s foaf:isPrimaryTopicOf <{wiki_url}> .
}}
LIMIT 20
"""
    rows = sparql_select(DBPEDIA_ENDPOINT, q)
    return [row["s"]["value"] for row in rows]

def align_yago(wiki_url: str) -> list[str]:
    # tenta alguns padrões comuns (YAGO varia bastante)
    candidates = [
        ("schema:sameAs", "http://schema.org/sameAs"),
        ("owl:sameAs", str(OWL.sameAs)),
        ("foaf:isPrimaryTopicOf", "http://xmlns.com/foaf/0.1/isPrimaryTopicOf"),
        ("schema:about", "http://schema.org/about"),
    ]

    out: list[str] = []
    for _, p in candidates:
        q = f"""
SELECT ?s WHERE {{
  ?s <{p}> <{wiki_url}> .
}}
LIMIT 20
"""
        try:
            rows = sparql_select(YAGO_ENDPOINT, q)
            out.extend(row["s"]["value"] for row in rows)
        except Exception:
            pass

        if out:
            break

    # remove duplicatas mantendo ordem
    seen = set()
    uniq = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq

def main() -> None:
    g_in = Graph()
    g_in.parse(IN_TTL, format="turtle")

    g_out = Graph()

    # schema:sameAs links
    schema_sameAs = URIRef("https://schema.org/sameAs")

    pairs = list(g_in.triples((None, schema_sameAs, None)))
    print(f"Loaded {len(pairs)} wikipedia links from {IN_TTL}")

    done = 0
    for subj, _, wiki in pairs:
        wiki_url = str(wiki)

        # DBpedia
        try:
            for dbp in align_dbpedia(wiki_url):
                g_out.add((subj, OWL.sameAs, URIRef(dbp)))
        except Exception:
            pass

        # YAGO
        try:
            for y in align_yago(wiki_url):
                g_out.add((subj, OWL.sameAs, URIRef(y)))
        except Exception:
            pass

        done += 1
        if done % 200 == 0:
            print(f"[progress] {done}/{len(pairs)} align_triples={len(g_out)}")
        time.sleep(0.01)  # evita rate-limit agressivo

    g_out.serialize(destination=OUT_TTL, format="turtle")
    print(f"Done. align_triples={len(g_out)} wrote={OUT_TTL}")

if __name__ == "__main__":
    main()