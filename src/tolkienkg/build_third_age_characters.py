from __future__ import annotations

from pathlib import Path

from rdflib import Graph

from .mediawiki import MediaWikiClient, WikitextCache
from .rdf_character import build_character_graph

CATEGORY = "Category:Third Age characters"
OUT_TTL = "kg/third_age_characters.ttl"


def main() -> None:
    client = MediaWikiClient()
    cache = WikitextCache()

    big = Graph()

    ok = 0
    skipped = 0

    for title in client.list_category_members(CATEGORY):
        try:
            wt = cache.get_or_fetch(client, title)
            g = build_character_graph(title, wt)

            # skip pages that didn't have infobox character (only minimal triples)
            # heuristic: if graph has only <=4 triples (page/resource basics), skip
            if len(g) <= 4:
                skipped += 1
                continue

            for t in g:
                big.add(t)

            ok += 1

            if ok % 50 == 0:
                print(f"[progress] ok={ok} skipped={skipped}")

        except Exception as e:
            skipped += 1
            print(f"[warn] {title}: {e}")

    Path("kg").mkdir(exist_ok=True)
    big.serialize(destination=OUT_TTL, format="turtle")
    print(f"Done. ok={ok} skipped={skipped} triples={len(big)} wrote={OUT_TTL}")


if __name__ == "__main__":
    main()