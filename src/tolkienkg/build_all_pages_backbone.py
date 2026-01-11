from __future__ import annotations

from pathlib import Path
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, RDFS

from .mediawiki import MediaWikiClient
from .namespaces import SCHEMA
from .iri import page_iri, resource_iri

OUT = "kg/allpages_backbone.ttl"
GRAPH_URI = "http://localhost:8000/graph/main"

def main(limit=None) -> None:
    mw = MediaWikiClient()
    titles = mw.list_all_pages(namespace=0, limit=limit)

    g = Graph()
    g.bind("schema", SCHEMA)
    g.bind("rdfs", RDFS)

    for t in titles:
        page = URIRef(page_iri(t))
        res = URIRef(resource_iri(t))

        g.add((page, RDF.type, SCHEMA.WebPage))
        g.add((page, SCHEMA.about, res))
        g.add((page, RDFS.label, Literal(t, lang="en")))
        g.add((res, RDFS.label, Literal(t, lang="en")))

    Path("kg").mkdir(exist_ok=True)
    g.serialize(destination=OUT, format="turtle")
    print(f"Wrote {OUT} with {len(titles)} pages and {len(g)} triples.")

if __name__ == "__main__":
    main(limit=None)