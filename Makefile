# Validation des data contracts. Voir README.md.
VENV   ?= .venv
PYTHON ?= $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)

.PHONY: install install-catalog catalog catalog-open publish schema lineage lineage-wip test check check-wip

install:
	python3 -m venv $(VENV)
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -e .

# Catalogue de donnees (dbt-colibri) : dependance optionnelle, hors make check.
install-catalog: install
	$(VENV)/bin/python -m pip install -e ".[catalog]"

# Catalogue : dist/catalog/index.html + colibri-manifest.json. Autonome : cree le venv et installe
# dbt-colibri au besoin, donc `make catalog` suffit pour n'importe quel collaborateur.
catalog:
	@test -x $(VENV)/bin/python && $(VENV)/bin/python -c "import dbt_colibri" 2>/dev/null || $(MAKE) install-catalog
	$(VENV)/bin/python tools/build_catalog.py $(ARGS)

# Publie le catalogue sur Cloudflare Pages (projet demo-odcs, voir wrangler.jsonc).
publish: catalog
	wrangler pages deploy dist/catalog --project-name demo-odcs --branch main

# Idem et ouvre le catalogue dans le navigateur.
catalog-open: ARGS=--open
catalog-open: catalog

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
