from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse, parse_qs, quote

from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from .config import TOLKIEN_GATEWAY_API
from .iri import resource_iri
from .mediawiki import MediaWikiClient
from .namespaces import SCHEMA

BACKBONE_TTL = "kg/allpages_backbone.ttl"
OUT_TTL = "kg/wikipedia_links.ttl"
CACHE_DIR = Path("cache/tg_parse_wikipedia_links")

# Aceitar várias “caras” possíveis de Wikipedia
WIKI_HOST_SUFFIX = "wikipedia.org"

# Preferência de normalização (o enunciado fala Wikipedia, TG é majoritariamente enwiki)
CANONICAL_WIKI_BASE = "http://en.wikipedia.org/wiki/"


def _hash_key(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _cache_path(title: str, prop: str) -> Path:
    key = _hash_key(f"{title}||{prop}")
    return CACHE_DIR / f"{key}.json"


def _read_cache(title: str, prop: str) -> dict[str, Any] | None:
    p = _cache_path(title, prop)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_cache(title: str, prop: str, obj: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(title, prop).write_text(
        json.dumps(obj, ensure_ascii=False), encoding="utf-8"
    )


def titles_from_backbone(base: str = "http://localhost:8000") -> list[str]:
    """
    Lê o backbone TTL e retorna os titles (strings) das páginas TG (a partir de schema:about).
    """
    from rdflib import Graph as RdfGraph
    from .namespaces import SCHEMA as _SCHEMA

    g = RdfGraph()
    g.parse(BACKBONE_TTL, format="turtle")

    titles: set[str] = set()
    for page in g.subjects(RDF.type, _SCHEMA.WebPage):
        for res in g.objects(page, _SCHEMA.about):
            res_str = str(res)
            if not res_str.startswith(f"{base}/resource/"):
                continue
            slug = res_str.split("/resource/", 1)[1]
            title = unquote(slug).replace("_", " ").strip()
            if title:
                titles.add(title)
    return sorted(titles)


def parse_prop(mw: MediaWikiClient, title: str, prop: str) -> dict[str, Any]:
    """
    Chama action=parse para uma prop específica e faz cache.
    """
    cached = _read_cache(title, prop)
    if cached is not None:
        return cached

    data = mw.get(
        {
            "action": "parse",
            "page": title,
            "prop": prop,
            "redirects": 1,
            "format": "json",
        }
    )

    # guarda mesmo se vier erro, pra não ficar repetindo chamada ruim
    if isinstance(data, dict):
        _write_cache(title, prop, data)
    return data if isinstance(data, dict) else {"error": {"info": "non-dict response"}}


def extract_externallinks(parse_json: dict[str, Any]) -> list[str]:
    p = parse_json.get("parse", {}) or {}
    links = p.get("externallinks") or []
    out: list[str] = []
    for x in links:
        if isinstance(x, str):
            out.append(x)
    return out


def extract_iwlinks(parse_json: dict[str, Any]) -> list[dict[str, Any]]:
    p = parse_json.get("parse", {}) or {}
    links = p.get("iwlinks") or []
    out: list[dict[str, Any]] = []
    for x in links:
        if isinstance(x, dict):
            out.append(x)
    return out


def _is_wikipedia_host(netloc: str) -> bool:
    netloc = netloc.lower()
    # netloc pode vir com porta, então remove
    netloc = netloc.split(":", 1)[0]
    return netloc.endswith(WIKI_HOST_SUFFIX)


def normalize_wikipedia_url(u: str) -> str | None:
    """
    Normaliza urls que apontam pra Wikipedia:
    - remove fragment (#...)
    - tenta transformar em https://en.wikipedia.org/wiki/TITLE
    Retorna None se não for wikipedia válida.
    """
    if not isinstance(u, str) or not u:
        return None

    # alguns casos podem vir como //en.wikipedia.org/wiki/...
    if u.startswith("//"):
        u = "http:" + u

    try:
        parsed = urlparse(u)
    except Exception:
        return None

    if parsed.scheme not in ("http", "https"):
        return None

    if not _is_wikipedia_host(parsed.netloc):
        return None

    # remove fragment
    parsed = parsed._replace(fragment="")

    # caso padrão /wiki/Title
    path = parsed.path or ""
    if path.startswith("/wiki/") and len(path) > len("/wiki/"):
        title = path.split("/wiki/", 1)[1]
        # não decodifica totalmente pra não quebrar unicode, mas normaliza espaços
        title = title.replace(" ", "_")
        return CANONICAL_WIKI_BASE + title

    # caso /w/index.php?title=Title
    if path.endswith("/w/index.php") or path.endswith("/w/index.php/"):
        qs = parse_qs(parsed.query or "")
        if "title" in qs and qs["title"]:
            title = qs["title"][0].replace(" ", "_")
            return CANONICAL_WIKI_BASE + title

    return None


def wikipedia_urls_from_iwlinks(iw: dict[str, Any]) -> Iterable[str]:
    """
    iwlinks costuma vir como dict com campos tipo:
    - prefix: "wikipedia" (ou variações)
    - url: "https://en.wikipedia.org/wiki/Elrond"
    - "*": "Elrond" (ou algo parecido)
    """
    prefix = str(iw.get("prefix", "") or "").lower().strip()
    url = iw.get("url")
    star = iw.get("*")

    # se já tem url direto, usa
    if isinstance(url, str):
        n = normalize_wikipedia_url(url)
        if n:
            yield n
            return

    # fallback: se prefix indica wikipedia e * parece ser título
    if prefix in ("wikipedia", "w", "wp"):
        if isinstance(star, str) and star.strip():
            title = star.strip().replace(" ", "_")
            # quote pra lidar com caracteres especiais
            safe_title = quote(title, safe="/:_()-")
            yield CANONICAL_WIKI_BASE + safe_title


def main(limit_pages: int | None = None, out_ttl: str = OUT_TTL) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    mw = MediaWikiClient(api_url=TOLKIEN_GATEWAY_API)

    titles = titles_from_backbone()
    if limit_pages is not None:
        titles = titles[:limit_pages]

    g = Graph()
    pages_with_wiki = 0
    wiki_links = 0

    for i, title in enumerate(titles, start=1):
        # 1) externallinks
        data_ext = parse_prop(mw, title, "externallinks")
        # 2) iwlinks (muito importante no TG)
        data_iw = parse_prop(mw, title, "iwlinks")

        urls: set[str] = set()

        if isinstance(data_ext, dict) and "parse" in data_ext and "error" not in data_ext:
            for u in extract_externallinks(data_ext):
                n = normalize_wikipedia_url(u)
                if n:
                    urls.add(n)

        if isinstance(data_iw, dict) and "parse" in data_iw and "error" not in data_iw:
            for iw in extract_iwlinks(data_iw):
                for u in wikipedia_urls_from_iwlinks(iw):
                    n = normalize_wikipedia_url(u) or u
                    # wikipedia_urls_from_iwlinks já tende a ser canonical, mas garante
                    n2 = normalize_wikipedia_url(n)
                    if n2:
                        urls.add(n2)

        if not urls:
            continue

        subj = URIRef(str(resource_iri(title)))
        for u in sorted(urls):
            g.add((subj, SCHEMA.sameAs, URIRef(u)))

        pages_with_wiki += 1
        wiki_links += len(urls)

        if i % 2000 == 0:
            print(
                f"[progress] i={i}/{len(titles)} pages_with_wiki={pages_with_wiki} wiki_links={wiki_links}"
            )

    g.serialize(destination=out_ttl, format="turtle")
    print(
        f"Done. pages_with_wiki={pages_with_wiki} wiki_links={wiki_links} triples={len(g)} wrote={out_ttl}"
    )


if __name__ == "__main__":
    main(limit_pages=11519)