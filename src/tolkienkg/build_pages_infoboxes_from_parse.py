from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import mwparserfromhell
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS

from .config import TOLKIEN_GATEWAY_API
from .iri import page_iri, resource_iri
from .mediawiki import MediaWikiClient
from .namespaces import SCHEMA, TG
from .rdf_character import build_character_graph

BACKBONE_TTL = "kg/allpages_backbone.ttl"
OUT_TTL = "kg/pages_infoboxes_from_parse.ttl"
CACHE_DIR = Path("cache/tg_parse_pages")


# ----------------------------
# Cache
# ----------------------------
def _hash_key(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _cache_path(title: str, props: str) -> Path:
    return CACHE_DIR / f"{_hash_key(title + '|' + props)}.json"


def _read_cache(title: str, props: str) -> dict[str, Any] | None:
    p = _cache_path(title, props)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_cache(title: str, props: str, obj: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(title, props).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


# ----------------------------
# MediaWiki parse wrapper
# ----------------------------
def parse_page(mw: MediaWikiClient, title: str, props: str) -> dict[str, Any]:
    cached = _read_cache(title, props)
    if cached is not None:
        return cached

    data = mw.get(
        {
            "action": "parse",
            "page": title,
            "prop": props,
            "redirects": 1,
            "format": "json",
        }
    )

    # não cacheia erros
    if isinstance(data, dict) and ("error" in data or "parse" not in data):
        return data

    _write_cache(title, props, data)
    return data


# ----------------------------
# Extractors
# ----------------------------
def extract_wikitext(parse_json: dict[str, Any]) -> str | None:
    p = parse_json.get("parse", {}) or {}
    wt = (p.get("wikitext") or {}).get("*")
    return wt


def extract_templates(parse_json: dict[str, Any]) -> list[str]:
    out: list[str] = []
    items = (parse_json.get("parse", {}) or {}).get("templates", []) or []
    for it in items:
        if isinstance(it, dict):
            name = it.get("*") or it.get("title")
            if name:
                out.append(str(name))
        elif isinstance(it, str):
            out.append(it)
    return out


def extract_links(parse_json: dict[str, Any]) -> list[str]:
    out: list[str] = []
    items = (parse_json.get("parse", {}) or {}).get("links", []) or []
    for it in items:
        if isinstance(it, dict):
            t = it.get("*") or it.get("title")
            if t:
                out.append(str(t))
    return out


def extract_images(parse_json: dict[str, Any]) -> list[str]:
    imgs = (parse_json.get("parse", {}) or {}).get("images", []) or []
    return [str(x) for x in imgs if x]


# ----------------------------
# Titles from backbone
# ----------------------------
def titles_from_backbone(backbone_path: str = BACKBONE_TTL, base: str = "http://localhost:8000") -> list[str]:
    g = Graph()
    g.parse(backbone_path, format="turtle")

    titles: set[str] = set()
    for page in g.subjects(RDF.type, SCHEMA.WebPage):
        for res in g.objects(page, SCHEMA.about):
            res_str = str(res)
            if not res_str.startswith(f"{base}/resource/"):
                continue
            slug = res_str.split("/resource/", 1)[1]
            title = unquote(slug).replace("_", " ").strip()
            if title:
                titles.add(title)

    return sorted(titles)


# ----------------------------
# Key sanitization (FIX)
# ----------------------------
def _safe_key(key: str) -> str:
    """
    Turn infobox param name into a safe TG predicate local name.
    - strip
    - lowercase
    - replace spaces and punctuation by underscores
    - collapse multiple underscores
    - avoid empty
    """
    k = key.strip().lower()
    # normalize accents -> keep ascii-ish for stability
    k = unicodedata.normalize("NFKD", k)
    k = "".join(ch for ch in k if not unicodedata.combining(ch))
    # replace anything non [a-z0-9_] with underscore
    k = re.sub(r"[^a-z0-9_]+", "_", k.replace(" ", "_"))
    k = re.sub(r"_+", "_", k).strip("_")
    return k or "param"


# ----------------------------
# Infobox detection + generic transformation
# ----------------------------
def _find_infobox_template_name(wikitext: str) -> str | None:
    code = mwparserfromhell.parse(wikitext)
    for tpl in code.filter_templates(recursive=False):
        name = str(tpl.name).strip().replace("_", " ")
        if "infobox" in name.lower():
            return name
    return None


def _extract_wikilinks(value: str) -> list[str]:
    titles: list[str] = []
    for m in re.finditer(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]", value):
        t = m.group(1).strip()
        if t:
            titles.append(t)
    return titles


def _class_from_infobox_name(tpl_name_lc: str) -> URIRef:
    """
    Decide which TG class to use based on infobox template name.
    Adjust the class local names here if your tg_vocab.ttl uses different ones.
    """
    # Default to TG:Thing-like class (still aligned via tg_vocab)
    # If you don't have tg:Entity, switch to TG["thing"] or TG["Thing"] etc.
    if "character" in tpl_name_lc or "person" in tpl_name_lc:
        return URIRef(str(TG["Character"]))
    if "location" in tpl_name_lc or "place" in tpl_name_lc:
        return URIRef(str(TG["Location"]))
    if "battle" in tpl_name_lc or "war" in tpl_name_lc:
        return URIRef(str(TG["Event"]))
    return URIRef(str(TG["Entity"]))


def build_generic_infobox_graph(page_title: str, wikitext: str) -> Graph:
    g = Graph()

    subj = URIRef(str(resource_iri(page_title)))
    g.add((subj, RDFS.label, Literal(page_title, lang="en")))

    code = mwparserfromhell.parse(wikitext)
    infobox_tpl = None
    for tpl in code.filter_templates(recursive=False):
        name = str(tpl.name).strip().replace("_", " ")
        if "infobox" in name.lower():
            infobox_tpl = tpl
            break
    if infobox_tpl is None:
        return g

    tpl_name_lc = str(infobox_tpl.name).strip().lower()
    g.add((subj, RDF.type, _class_from_infobox_name(tpl_name_lc)))

    for p in infobox_tpl.params:
        key = str(p.name).strip()
        val = str(p.value).strip()
        if not key:
            continue

        k = _safe_key(key)
        pred = TG[k]
        links = _extract_wikilinks(val)

        if links:
            for t in links:
                g.add((subj, pred, URIRef(str(resource_iri(t)))))
            g.add((subj, TG[f"{k}_raw"], Literal(val, lang="en")))
        else:
            g.add((subj, pred, Literal(val, lang="en")))

    return g


# ----------------------------
# Main
# ----------------------------
def main(
    limit_pages: int | None = None,
    props: str = "wikitext|templates|links|images",
    out_ttl: str = OUT_TTL,
) -> None:
    Path("kg").mkdir(exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    mw = MediaWikiClient(api_url=TOLKIEN_GATEWAY_API)
    titles = titles_from_backbone(BACKBONE_TTL)

    if limit_pages is not None:
        titles = titles[:limit_pages]

    big = Graph()
    ok = 0
    skipped = 0
    errors = 0

    for i, title in enumerate(titles, start=1):
        try:
            data = parse_page(mw, title, props=props)
            if "error" in data or "parse" not in data:
                skipped += 1
                continue

            wikitext = extract_wikitext(data)
            if not wikitext:
                skipped += 1
                continue

            # “if applicable”: só processa se houver infobox
            infobox_name = _find_infobox_template_name(wikitext)
            if not infobox_name:
                skipped += 1
                continue

            # monta grafo da página localmente (evita lixo parcial se der erro)
            page_graph = Graph()

            # usar sua procedure forte quando for Infobox character
            norm = infobox_name.lower().replace("_", " ").strip()
            if "infobox character" in norm:
                g = build_character_graph(title, wikitext)
            else:
                g = build_generic_infobox_graph(title, wikitext)

            # se só tem label + type (ou só label), não conta
            if len(g) <= 2:
                skipped += 1
                continue

            for t in g:
                page_graph.add(t)

            # page triples (forçando URIRef)
            p = URIRef(str(page_iri(title)))
            r = URIRef(str(resource_iri(title)))

            page_graph.add((p, RDF.type, SCHEMA.WebPage))
            page_graph.add((p, SCHEMA.about, r))

            # links -> schema:mentions
            for lk in extract_links(data):
                lk_title = lk.replace("_", " ").strip()
                if lk_title:
                    page_graph.add((p, SCHEMA.mentions, URIRef(str(resource_iri(lk_title)))))

            # images -> schema:image (deixando pra “depois” a URL final, por enquanto literal do filename)
            for img in extract_images(data):
                page_graph.add((p, SCHEMA.image, Literal(img, lang="en")))

            # templates -> tg:template
            for tpl in extract_templates(data):
                tpl_name = tpl.replace("_", " ").strip()
                if tpl_name:
                    page_graph.add((p, TG.template, Literal(tpl_name, lang="en")))

            # só aqui “commitamos” no big
            for t in page_graph:
                big.add(t)

            ok += 1
            if i % 500 == 0:
                print(f"[progress] i={i}/{len(titles)} ok={ok} skipped={skipped} errors={errors}")

        except Exception as e:
            errors += 1
            if errors <= 25:
                print(f"[warn] {title}: {e}")

    big.serialize(destination=out_ttl, format="turtle")
    print(f"Done. pages={len(titles)} ok={ok} skipped={skipped} errors={errors} triples={len(big)} wrote={out_ttl}")


if __name__ == "__main__":
    main()