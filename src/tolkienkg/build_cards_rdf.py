from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, RDFS

from .namespaces import SCHEMA

BASE = "http://localhost:8000"
CARDS_JSON = "data/cards.json"
BACKBONE_TTL = "kg/allpages_backbone.ttl"

OUT_TTL = "kg/cards.ttl"
OUT_UNMATCHED = "kg/cards_unmatched.txt"


def card_iri(card_id: str) -> URIRef:
    return URIRef(f"{BASE}/card/{quote(card_id, safe='')}")

def resource_iri_from_title(title: str) -> URIRef:
    slug = quote(title.replace(" ", "_"), safe="")
    return URIRef(f"{BASE}/resource/{slug}")


def load_resource_label_index(backbone_ttl: str) -> dict[str, URIRef]:
    """
    Build mapping: English label -> resource IRI (only for http://localhost:8000/resource/*).
    """
    g = Graph()
    g.parse(backbone_ttl, format="turtle")

    idx: dict[str, URIRef] = {}
    for s, p, o in g.triples((None, RDFS.label, None)):
        if not isinstance(o, Literal):
            continue
        if o.language != "en":
            continue
        s_str = str(s)
        if not s_str.startswith(f"{BASE}/resource/"):
            continue
        idx[str(o)] = URIRef(s)

    return idx


def main() -> None:
    # Load cards.json
    data = json.loads(Path(CARDS_JSON).read_text(encoding="utf-8"))

    # Index existing KG entities by label (from backbone)
    label_to_resource = load_resource_label_index(BACKBONE_TTL)

    g = Graph()
    g.bind("schema", SCHEMA)
    g.bind("rdfs", RDFS)

    total = 0
    matched = 0
    unmatched: list[str] = []

    # cards.json structure: sets -> dict -> "cards" dict
    for set_id, set_obj in data.items():
        cards = set_obj.get("cards", {})
        for card_id, card in cards.items():
            total += 1
            c_iri = card_iri(card_id)

            # Basic typing + identifiers
            g.add((c_iri, RDF.type, SCHEMA.CreativeWork))
            g.add((c_iri, SCHEMA.identifier, Literal(card_id)))
            g.add((c_iri, SCHEMA.isPartOf, URIRef(f"{BASE}/cardset/{quote(set_id, safe='')}")))

            # Multilingual name -> rdfs:label
            name_by_lang = card.get("name", {}) or {}
            for lang, name in name_by_lang.items():
                if name:
                    g.add((c_iri, RDFS.label, Literal(name, lang=lang)))

            # Multilingual text -> schema:description
            text_by_lang = card.get("text", {}) or {}
            for lang, text in text_by_lang.items():
                if text:
                    g.add((c_iri, SCHEMA.description, Literal(text, lang=lang)))

            # Multilingual quote -> schema:quotation (se existir)
            quote_by_lang = card.get("quote", {}) or {}
            for lang, q in quote_by_lang.items():
                if q:
                    g.add((c_iri, SCHEMA.quotation, Literal(q, lang=lang)))

            # Link to KG entity by English name (best effort)
            en_name = (name_by_lang.get("en") or "").strip()
            if en_name and en_name in label_to_resource:
                r_iri = label_to_resource[en_name]
                g.add((c_iri, SCHEMA.about, r_iri))
                g.add((r_iri, SCHEMA.subjectOf, c_iri))
                matched += 1
            else:
                if en_name:
                    unmatched.append(f"{card_id}\t{en_name}")
                else:
                    unmatched.append(f"{card_id}\t<no en name>")

    Path("kg").mkdir(exist_ok=True)
    g.serialize(destination=OUT_TTL, format="turtle")
    Path(OUT_UNMATCHED).write_text("\n".join(unmatched), encoding="utf-8")

    print(f"Wrote {OUT_TTL}")
    print(f"Cards total: {total}")
    print(f"Matched to KG entities (by en label): {matched}")
    print(f"Unmatched list saved: {OUT_UNMATCHED}")


if __name__ == "__main__":
    main()