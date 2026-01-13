from __future__ import annotations

import re
import unicodedata
import mwparserfromhell
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, RDFS

from tolkienkg.namespaces import SCHEMA, TG
from tolkienkg.iri import page_iri, resource_iri
from tolkienkg.infobox_characters import extract_infobox_character


def _key_to_predicate(key: str) -> URIRef:
    k = key.strip().lower()
    k = unicodedata.normalize("NFKD", k)
    k = "".join(ch for ch in k if not unicodedata.combining(ch))
    k = re.sub(r"[^a-z0-9_]+", "_", k.replace(" ", "_"))
    k = re.sub(r"_+", "_", k).strip("_")
    k = k or "param"
    return TG[k]


def _extract_wikilinks(value: str) -> list[str]:
    """
    Extrai targets de [[...]] do wikitext do campo.
    """
    code = mwparserfromhell.parse(value or "")
    out: list[str] = []
    for wl in code.filter_wikilinks():
        target = str(wl.title).strip()
        if target:
            out.append(target)
    return out


def _is_bad_target(title: str) -> bool:
    # ignora namespaces como Category:, File:, Help:, Special:
    return ":" in title


def _raw_predicate(pred: URIRef) -> URIRef:
    """
    tg:<field>_raw (seguro, sem depender de split bizarro)
    """
    local = str(pred)
    local = local.rsplit("/", 1)[-1]
    return TG[f"{local}_raw"]


def build_character_graph(title: str, wikitext: str) -> Graph:
    g = Graph()
    g.bind("schema", SCHEMA)
    g.bind("rdfs", RDFS)
    g.bind("tg", TG)

    page = URIRef(page_iri(title))
    ent = URIRef(resource_iri(title))

    # Backbone mínimo (page -> about -> resource)
    g.add((page, RDF.type, SCHEMA.WebPage))
    g.add((page, SCHEMA.about, ent))
    g.add((page, RDFS.label, Literal(title, lang="en")))

    # Entidade
    g.add((ent, RDF.type, SCHEMA.Person))
    g.add((ent, RDF.type, TG.Character))
    g.add((ent, RDFS.label, Literal(title, lang="en")))

    infobox = extract_infobox_character(wikitext)
    if not infobox:
        return g

    for key, raw_value in infobox.params.items():
        raw_value = (raw_value or "").strip()

        # se o campo existe mas veio vazio, melhor não poluir o grafo
        if raw_value == "":
            continue

        pred = _key_to_predicate(key)
        links = [t for t in _extract_wikilinks(raw_value) if not _is_bad_target(t)]

        if links:
            for target in links:
                g.add((ent, pred, URIRef(resource_iri(target))))
            g.add((ent, _raw_predicate(pred), Literal(raw_value, lang="en")))
        else:
            # literal "sujo" (fica pra limpeza posterior)
            g.add((ent, pred, Literal(raw_value, lang="en")))

    return g