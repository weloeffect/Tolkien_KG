from __future__ import annotations

from pathlib import Path
import re

import mwparserfromhell
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, RDFS

from tolkienkg.namespaces import SCHEMA, TG
from tolkienkg.iri import page_iri, resource_iri
from tolkienkg.infobox_characters import extract_infobox_character

def _key_to_predicate(key: str) -> URIRef:
    k = key.strip().lower()
    k = re.sub(r"[^a-z0-9]+", "_", k).strip("_")
    return TG[k]


def _extract_wikilinks(value: str) -> list[str]:
    code = mwparserfromhell.parse(value)
    out = []
    for wl in code.filter_wikilinks():
        target = str(wl.title).strip()
        if target:
            out.append(target)
    return out


def _is_bad_target(title: str) -> bool:
    # Ignore non-main namespace and special pages
    # Examples: "Category:...", "File:...", "Help:...", "Special:..."
    return ":" in title


def build_character_graph(title: str, wikitext: str) -> Graph:
    g = Graph()
    g.bind("schema", SCHEMA)
    g.bind("rdfs", RDFS)
    g.bind("tg", TG)

    page = URIRef(page_iri(title))
    ent = URIRef(resource_iri(title))

    g.add((page, RDF.type, SCHEMA.WebPage))
    g.add((page, SCHEMA.about, ent))
    g.add((page, RDFS.label, Literal(title, lang="en")))

    g.add((ent, RDF.type, SCHEMA.Person))
    g.add((ent, RDFS.label, Literal(title, lang="en")))

    infobox = extract_infobox_character(wikitext)
    if not infobox:
        # No infobox character: return minimal graph (or raise; your choice)
        return g

    for key, raw_value in infobox.params.items():
        pred = _key_to_predicate(key)
        links = [t for t in _extract_wikilinks(raw_value) if not _is_bad_target(t)]

        if links:
            for target in links:
                g.add((ent, pred, URIRef(resource_iri(target))))
            g.add((ent, TG[f"{pred.split('/')[-1]}_raw"], Literal(raw_value, lang="en")))
        else:
            # keep literal (even if noisy; we’ll clean in next commit)
            g.add((ent, pred, Literal(raw_value, lang="en")))

    return g