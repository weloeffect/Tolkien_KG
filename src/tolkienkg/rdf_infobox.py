from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS
import urllib.parse

SCHEMA = Namespace("https://schema.org/")
TG = Namespace("http://localhost:8000/vocab/")

TEMPLATE_TO_CLASS = {
    "infobox_character": SCHEMA.Person,
    "person_infobox": SCHEMA.Person,
    "people_infobox": SCHEMA.Person,
    "actor": SCHEMA.Person,
    "director": SCHEMA.Person,
    "author_infobox": SCHEMA.Person,
    "artist_infobox": SCHEMA.Person,
    "location_infobox": SCHEMA.Place,
    "mountain": SCHEMA.Place,
    "kingdom": SCHEMA.Place,
    "organization_infobox": SCHEMA.Organization,
    "company_infobox": SCHEMA.Organization,
    "book": SCHEMA.Book,
    "journal": SCHEMA.CreativeWork,
    "poem_infobox": SCHEMA.CreativeWork,
    "song": SCHEMA.CreativeWork,
    "battle": SCHEMA.Event,
    "war": SCHEMA.Event,
    "film_infobox": SCHEMA.Movie,
    "video_game_infobox": SCHEMA.VideoGame,
    "plant_infobox": SCHEMA.Taxon,
}

def build_infobox_graph(page_title: str, template_name: str, infobox: dict) -> Graph:
    g = Graph()
    g.bind("schema", SCHEMA)
    g.bind("tg", TG)

    slug = urllib.parse.quote(page_title.replace(" ", "_"))
    resource_uri = URIRef(f"http://localhost:8000/resource/{slug}")
    page_uri = URIRef(f"http://localhost:8000/page/{slug}")

    g.add((page_uri, RDF.type, SCHEMA.WebPage))
    g.add((page_uri, RDFS.label, Literal(page_title, lang="en")))
    g.add((page_uri, SCHEMA.about, resource_uri))

    template_key = template_name.replace("Template:", "").lower().replace(" ", "_")
    rdf_class = TEMPLATE_TO_CLASS.get(template_key, SCHEMA.Thing)
    g.add((resource_uri, RDF.type, rdf_class))

    g.add((resource_uri, TG.infoboxTemplate,
           URIRef(f"http://localhost:8000/template/{template_key}")))

    for key, val in infobox.items():
        if not val:
            continue
        pred = TG[key]
        if "[[" in val and "]]" in val:
            # Wikilink: extract target
            target = val.replace("[[", "").replace("]]", "").split("|")[0].strip()
            link_uri = URIRef(f"http://localhost:8000/resource/{urllib.parse.quote(target.replace(' ', '_'))}")
            g.add((resource_uri, pred, link_uri))
        else:
            g.add((resource_uri, pred, Literal(val, lang="en")))

    return g