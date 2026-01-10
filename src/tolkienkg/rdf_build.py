from __future__ import annotations

from pathlib import Path
import re

import mwparserfromhell
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, RDFS

from tolkienkg.namespaces import SCHEMA, TG
from tolkienkg.iri import page_iri, resource_iri
from tolkienkg.infobox_parser import parse_infobox_from_file


def _key_to_predicate(key: str) -> URIRef:
    # tg:realm, tg:race, tg:spouse... (normaliza)
    k = key.strip().lower()
    k = re.sub(r"[^a-z0-9]+", "_", k).strip("_")
    return TG[k]


def _extract_wikilinks(value: str) -> list[str]:
    """Return targets of [[...]] links. Handles [[Title]] and [[Title|label]]."""
    code = mwparserfromhell.parse(value)
    links = []
    for wl in code.filter_wikilinks():
        target = str(wl.title).strip()
        if target:
            links.append(target)
    return links


def build_elrond_graph(infobox_path: str | Path) -> Graph:
    g = Graph()
    g.bind("schema", SCHEMA)
    g.bind("rdfs", RDFS)
    g.bind("tg", TG)

    title = "Elrond"

    page = URIRef(page_iri(title))
    ent = URIRef(resource_iri(title))

    # Page vs entity (Stage 0 decision)
    g.add((page, RDF.type, SCHEMA.WebPage))
    g.add((page, SCHEMA.about, ent))
    g.add((page, RDFS.label, Literal("Elrond", lang="en")))

    # Entity typing (minimal, you can refine later)
    g.add((ent, RDF.type, SCHEMA.Person))
    g.add((ent, RDFS.label, Literal("Elrond", lang="en")))

    infobox = parse_infobox_from_file(infobox_path)

    # Encode: each infobox field becomes a triple ent tg:<field> <value>
    for key, raw_value in infobox.params.items():
        pred = _key_to_predicate(key)

        # If value contains wiki links, encode links as entity IRIs
        links = _extract_wikilinks(raw_value)

        if links:
            for target in links:
                g.add((ent, pred, URIRef(resource_iri(target))))
            # Optional: also keep the raw text as literal for traceability
            g.add((ent, TG[f"{_key_to_predicate(key).split('/')[-1]}_raw"], Literal(raw_value, lang="en")))
        else:
            # plain literal
            g.add((ent, pred, Literal(raw_value, lang="en")))

    return g

def main() -> None:
    g = build_elrond_graph("data/wikitext/elrond_infobox.wiki")
    Path("kg").mkdir(exist_ok=True)
    g.serialize(destination="kg/elrond.ttl", format="turtle")
    print("Wrote kg/elrond.ttl")

if __name__ == "__main__":
    main()