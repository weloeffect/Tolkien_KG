from rdflib import Namespace

SCHEMA = Namespace("https://schema.org/")
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
OWL = Namespace("http://www.w3.org/2002/07/owl#")

# Custom namespace (minimal, only when needed)
TG = Namespace("http://localhost:8000/vocab/")