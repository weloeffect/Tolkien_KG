# TolkienKG (Semantic Web Final Project)

## Stage 0
repository scaffold + IRI policy + namespaces (schema.org).

## Setup
```
python -m venv .venv
```

```
source .venv/bin/activate
```

```
pip install -r requirements.txt
```

## Stage 1 – Fuseki

## Run Fuseki (local)
```
./scripts/setup_fuseki.sh
./scripts/start_fuseki.sh
```

## Smoke test
```
./scripts/smoke_test_fuseki.sh
```
```
Fuseki UI: http://localhost:3030
```
```
SPARQL endpoint: http://localhost:3030/tolkien/sparql
```

## Stage 2 – RDF Elrond
Run the 
```
scr/tolkienkg/rdf_build.py
```
