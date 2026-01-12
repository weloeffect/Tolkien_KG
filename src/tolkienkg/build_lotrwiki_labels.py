from __future__ import annotations

import json
import hashlib
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, quote

import requests
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDFS, OWL

BASE = "http://localhost:8000"
LOTR_API = "https://lotr.fandom.com/api.php"

BACKBONE_TTL = "kg/allpages_backbone.ttl"
OUT_TTL = "kg/lotrwiki_labels.ttl"
OUT_LOG = "kg/lotrwiki_labels.log"

CACHE_DIR = Path("cache/lotrwiki")
CACHE_RESOLVE = CACHE_DIR / "resolve"
CACHE_LANGLINKS = CACHE_DIR / "langlinks"


def ensure_dirs() -> None:
    CACHE_RESOLVE.mkdir(parents=True, exist_ok=True)
    CACHE_LANGLINKS.mkdir(parents=True, exist_ok=True)
    Path("kg").mkdir(parents=True, exist_ok=True)


def safe_filename(s: str, prefix_len: int = 40) -> str:
    """
    Return a filesystem-safe filename for arbitrary strings.
    Uses a hash to avoid macOS 'File name too long'.
    """
    h = hashlib.sha1(s.encode("utf-8")).hexdigest()
    # keep a small readable prefix (optional)
    prefix = s.strip().replace(" ", "_")
    prefix = "".join(ch for ch in prefix if ch.isalnum() or ch in ("_", "-"))
    prefix = prefix[:prefix_len] if prefix else "x"
    return f"{prefix}__{h}"


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def resource_title_from_iri(res_iri: str) -> str | None:
    if not res_iri.startswith(f"{BASE}/resource/"):
        return None
    slug = res_iri.split("/resource/", 1)[1]
    title = unquote(slug).replace("_", " ")
    return title.strip() if title.strip() else None


def lotr_page_iri(title: str) -> URIRef:
    # canonical EN page
    t = title.replace(" ", "_")
    return URIRef(f"https://lotr.fandom.com/wiki/{quote(t, safe='_()!-.,~%')}")


def lotr_query(params: dict[str, Any]) -> dict[str, Any]:
    r = requests.get(LOTR_API, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def resolve_lotr_title(title: str, sleep_s: float = 0.0) -> str | None:
    """
    Resolve a title in LOTR Wiki using action=query&titles=...&redirects=1
    Returns the canonical page title (as LOTR wiki uses).
    """
    cache_path = CACHE_RESOLVE / f"{safe_filename(title)}.json"
    cached = read_json(cache_path)
    if cached is not None:
        return cached.get("resolved_title")

    data = lotr_query({
        "action": "query",
        "format": "json",
        "redirects": "1",
        "titles": title,
    })

    pages = (data.get("query", {}) or {}).get("pages", {}) or {}
    # pages is a dict keyed by pageid (string); if missing, it can contain "-1"
    resolved = None
    for pid, page in pages.items():
        if str(pid) == "-1" or page.get("missing") is not None:
            resolved = None
        else:
            resolved = page.get("title")
        break

    write_json(cache_path, {"resolved_title": resolved, "raw": data})
    if sleep_s:
        time.sleep(sleep_s)
    return resolved


def fetch_langlinks(resolved_title: str, sleep_s: float = 0.0) -> dict[str, str]:
    """
    Get langlinks for a LOTR wiki page title. Handles llcontinue.
    Returns mapping {lang: title_in_lang}. Includes 'en' itself.
    """
    cache_path = CACHE_LANGLINKS / f"{safe_filename(resolved_title)}.json"
    cached = read_json(cache_path)
    if cached is not None:
        return cached.get("langlinks", {})

    langmap: dict[str, str] = {"en": resolved_title}
    llcontinue = None

    while True:
        params: dict[str, Any] = {
            "action": "query",
            "format": "json",
            "prop": "langlinks",
            "titles": resolved_title,
            "lllimit": "500",
            "redirects": "1",
        }
        if llcontinue:
            params["llcontinue"] = llcontinue

        data = lotr_query(params)
        pages = (data.get("query", {}) or {}).get("pages", {}) or {}

        for _, page in pages.items():
            for ll in page.get("langlinks", []) or []:
                lang = ll.get("lang")
                t = ll.get("*")
                if lang and t and lang not in langmap:
                    langmap[lang] = t

        llcontinue = (data.get("continue", {}) or {}).get("llcontinue")
        if not llcontinue:
            break

        if sleep_s:
            time.sleep(sleep_s)

    write_json(cache_path, {"langlinks": langmap})
    return langmap


def main(limit_resources: int | None = 2000, sleep_s: float = 0.0) -> None:
    ensure_dirs()

    # Load backbone and extract resource IRIs
    bg = Graph()
    bg.parse(BACKBONE_TTL, format="turtle")

    resource_iris: list[str] = []
    for s in set(bg.subjects(RDFS.label, None)):
        s_str = str(s)
        if s_str.startswith(f"{BASE}/resource/"):
            resource_iris.append(s_str)

    resource_iris.sort()
    if limit_resources is not None:
        resource_iris = resource_iris[:limit_resources]

    out = Graph()
    out.bind("rdfs", RDFS)
    out.bind("owl", OWL)

    log_lines: list[str] = []
    ok = 0
    missing = 0

    for i, res_iri in enumerate(resource_iris, start=1):
        title = resource_title_from_iri(res_iri)
        if not title:
            continue

        resolved = resolve_lotr_title(title, sleep_s=sleep_s)
        if not resolved:
            missing += 1
            if missing <= 200:
                log_lines.append(f"MISSING\t{title}")
            continue

        try:
            ll = fetch_langlinks(resolved, sleep_s=sleep_s)
        except Exception as e:
            log_lines.append(f"ERROR\t{title}\tresolved={resolved}\t{e}")
            continue

        subj = URIRef(res_iri)

        # sameAs to LOTR wiki EN page
        out.add((subj, OWL.sameAs, lotr_page_iri(resolved)))

        # multilingual labels
        for lang, label in ll.items():
            # rdflib accepts BCP47-like tags; 'pt-br' is fine
            out.add((subj, RDFS.label, Literal(label, lang=lang)))

        ok += 1
        if i % 200 == 0:
            print(f"processed={i} ok={ok} missing={missing}")

    out.serialize(destination=OUT_TTL, format="turtle")
    Path(OUT_LOG).write_text("\n".join(log_lines), encoding="utf-8")

    print(f"Wrote {OUT_TTL} triples={len(out)}")
    print(f"ok={ok} missing={missing} (see {OUT_LOG})")


if __name__ == "__main__":
    # Comece com 2000 e depois suba pra None se quiser exaustivo.
    main(limit_resources=None, sleep_s=0.0)