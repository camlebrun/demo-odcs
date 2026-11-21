"""Utilitaires partages par les outils de validation."""
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_GLOB = "*.odcs.yaml"


class _Loader(yaml.SafeLoader):
    """SafeLoader qui garde les dates/timestamps en chaines (le schema ODCS les type string)."""


_Loader.yaml_implicit_resolvers = {
    key: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as fh:
        return yaml.load(fh, Loader=_Loader)  # noqa: S506 - loader derive de SafeLoader


def find_contracts(root: Path) -> list[Path]:
    """Tous les contrats sous <root>/contracts, tries."""
    return sorted((root / "contracts").rglob(CONTRACT_GLOB))
