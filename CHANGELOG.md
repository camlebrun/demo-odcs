# Changelog

Ce fichier suit le format [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Il décrit l'évolution du dépôt (outillage, conventions, ensemble des contrats). Chaque contrat porte sa propre version semver dans son champ `version` (voir `docs/conventions.md`).

## [Unreleased]

## [0.1.0]

### Ajouté
- Socle du dépôt : schéma JSON officiel ODCS v3.2.0 (`schema/odcs-v3.2.0.schema.json`), conventions (`docs/conventions.md`), outils `tools/validate_schema.py` et `tools/validate_lineage.py`, tests pytest avec fixtures valides et cassées, `Makefile`, CI GitHub Actions, `CODEOWNERS`, modèle de PR.
- Contrat témoin `raw__orders__shopify` (1.0.0), modèle des contrats suivants.
