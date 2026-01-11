import os
from src.tolkienkg.mediawiki import MediaWikiClient, WikitextCache
from src.tolkienkg.infobox_generic import extract_infobox
from src.tolkienkg.rdf_infobox import build_infobox_graph

OUT_DIR = "kg/infobox_templates"
os.makedirs(OUT_DIR, exist_ok=True)

def main():
    mw = MediaWikiClient()
    cache = WikitextCache()

    print("Fetching list of infobox templates...")
    templates = mw.list_category_members("Category:Infobox_templates", namespace=10)
    print(f"Found {len(templates)} templates.")

    for template_title in templates:
        print(f"\n=== Processing {template_title} ===")
        pages = mw.list_embeddedin(template_title, namespace=0, limit=50)

        if not pages:
            print(f"No pages found for {template_title}, skipping.")
            continue

        g_all = None

        for page in pages[:]:
            print(f"  -> {page}")
            wikitext = cache.get_or_fetch(mw, page)
            infobox = extract_infobox(wikitext, template_title)

            if not infobox:
                continue

            g = build_infobox_graph(page, template_title, infobox)
            if g_all is None:
                g_all = g
            else:
                g_all += g

        if g_all:
            fname = template_title.replace("Template:", "").replace(" ", "_").lower()
            out_path = os.path.join(OUT_DIR, f"{fname}.ttl")
            g_all.serialize(destination=out_path, format="turtle")
            print(f"Saved {out_path}")
        else:
            print(f"No infobox extracted for {template_title}")

if __name__ == "__main__":
    main()