# Validation des data contracts. Voir README.md.
VENV   ?= .venv
PYTHON ?= $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)

.PHONY: install schema lineage lineage-wip test check check-wip

install:
	python3 -m venv $(VENV)
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -e .

schema:
	$(PYTHON) tools/validate_schema.py

# Strict : exige le decompte final (14 raw + 3 customer).
lineage:
	$(PYTHON) tools/validate_lineage.py

# Travail en cours : memes regles, sans le decompte.
lineage-wip:
	$(PYTHON) tools/validate_lineage.py --no-count

test:
	$(PYTHON) -m pytest -q

# Controle final (CI) : schema + lineage strict + tests.
check: schema lineage test

# Controle pendant la construction du repo (decompte desactive).
check-wip: schema lineage-wip test
