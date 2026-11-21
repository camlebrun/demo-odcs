#!/usr/bin/env python3
"""Valide chaque contrat contracts/**/*.odcs.yaml contre le JSON Schema ODCS v3.2.0.

Code retour 0 si tout est valide, 1 sinon. Un message par erreur, avec le chemin du champ.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft201909Validator
from jsonschema.exceptions import best_match

from common import REPO_ROOT, find_contracts, load_yaml

SCHEMA_PATH = REPO_ROOT / "schema" / "odcs-v3.2.0.schema.json"


def format_path(error) -> str:
    out = ""
    for part in error.absolute_path:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out or "<racine>"


def leaf(error):
    """Descend dans les sous-erreurs (oneOf, anyOf, if/then) pour un message lisible."""
    while error.context:
        error = best_match(error.context)
    return error


def validate_file(path: Path, validator: Draft201909Validator) -> list[str]:
    try:
        data = load_yaml(path)
    except yaml.YAMLError as exc:
        return [f"YAML invalide: {exc}"]
    if not isinstance(data, dict):
        return ["le contrat doit etre un objet YAML"]
    messages = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(map(str, e.absolute_path))):
        err = leaf(err)
        message = f"{format_path(err)}: {err.message}"
        if message not in messages:
            messages.append(message)
    return messages


def run(root: Path, schema_path: Path = SCHEMA_PATH) -> dict[Path, list[str]]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft201909Validator(schema)
    return {p: validate_file(p, validator) for p in find_contracts(root)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="racine contenant contracts/")
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH)
    args = parser.parse_args(argv)

    results = run(args.root, args.schema)
    if not results:
        print(f"ERREUR: aucun contrat *.odcs.yaml sous {args.root / 'contracts'}", file=sys.stderr)
        return 1
    failed = 0
    for path, messages in results.items():
        rel = path.relative_to(args.root)
        for msg in messages:
            print(f"[SCHEMA] {rel}: {msg}")
        failed += bool(messages)
    if failed:
        print(f"\n{failed} contrat(s) invalide(s) sur {len(results)}.", file=sys.stderr)
        return 1
    print(f"OK schema ODCS v3.2.0: {len(results)} contrat(s) valide(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
