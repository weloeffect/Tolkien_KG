from rdflib import Graph
from pyshacl import validate

DATA_TTL = "kg/pages_infoboxes_from_parse.ttl"
SHAPES_TTL = "kg/tg_shapes.ttl"
OUT_REPORT_TTL = "kg/shacl_report.ttl"

def main():
    data_g = Graph()
    data_g.parse(DATA_TTL, format="turtle")

    shapes_g = Graph()
    shapes_g.parse(SHAPES_TTL, format="turtle")

    conforms, report_graph, report_text = validate(
        data_graph=data_g,
        shacl_graph=shapes_g,
        inference="rdfs",     # pode trocar por None se quiser mais “seco”
        advanced=True,
        abort_on_first=False,
        meta_shacl=False,
        debug=False,
    )

    print("CONFORMS:", conforms)
    print(report_text)

    report_graph.serialize(destination=OUT_REPORT_TTL, format="turtle")
    print("Wrote report to:", OUT_REPORT_TTL)

if __name__ == "__main__":
    main()