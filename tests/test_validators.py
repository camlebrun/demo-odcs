"""Tests des outils de validation.

- fixtures/valid/*  : mini-depots qui doivent passer schema + lineage.
- fixtures/broken/* : un cas casse par regle. expect.txt contient le code attendu (L00x ou
  SCHEMA), un extrait du message attendu, et optionnellement `strict` (decompte actif).
  Le test verifie que le code ET le message attendus sont produits.
"""
from pathlib import Path

import pytest

import validate_lineage
import validate_schema
from common import REPO_ROOT, load_yaml

FIXTURES = Path(__file__).parent / "fixtures"
VALID = sorted(p for p in (FIXTURES / "valid").iterdir() if p.is_dir())
BROKEN = sorted(p for p in (FIXTURES / "broken").iterdir() if p.is_dir())


def expectation(case: Path):
    lines = (case / "expect.txt").read_text(encoding="utf-8").splitlines()
    return lines[0], lines[1], "strict" in lines[2:]


def schema_errors(root: Path) -> list[str]:
    return [m for msgs in validate_schema.run(root).values() for m in msgs]


@pytest.mark.parametrize("case", VALID, ids=lambda p: p.name)
def test_valid_fixture_passes_schema_and_lineage(case):
    assert schema_errors(case) == []
    assert validate_lineage.run(case, count=False) == []


@pytest.mark.parametrize("case", BROKEN, ids=lambda p: p.name)
def test_broken_fixture_fails_for_the_expected_reason(case):
    code, snippet, strict = expectation(case)
    if code == "SCHEMA":
        messages = schema_errors(case)
        assert any(snippet in m for m in messages), messages
        return
    # Un cas L0xx doit etre un contrat ODCS valide : seule la regle visee casse.
    assert schema_errors(case) == []
    errors = validate_lineage.run(case, count=strict)
    assert any(e.code == code and snippet in e.message for e in errors), [str(e) for e in errors]


def test_each_rule_has_a_broken_fixture():
    codes = {expectation(c)[0] for c in BROKEN}
    expected = {f"L{n:03d}" for n in range(1, 21)} | {"SCHEMA"}
    assert expected <= codes, sorted(expected - codes)


def test_count_is_disabled_by_no_count():
    case = FIXTURES / "broken" / "l001_count"
    assert any(e.code == "L001" for e in validate_lineage.run(case, count=True))
    assert not any(e.code == "L001" for e in validate_lineage.run(case, count=False))


def test_cli_exit_codes():
    broken = str(FIXTURES / "broken" / "l003_unknown_property")
    valid = str(FIXTURES / "valid" / "mini_repo")
    assert validate_lineage.main(["--root", broken, "--no-count"]) == 1
    assert validate_lineage.main(["--root", valid, "--no-count"]) == 0
    assert validate_lineage.main(["--root", valid]) == 1  # decompte strict
    assert validate_schema.main(["--root", str(FIXTURES / "broken" / "schema_missing_version")]) == 1
    assert validate_schema.main(["--root", valid]) == 0


def test_cli_fails_when_no_contract(tmp_path):
    assert validate_schema.main(["--root", str(tmp_path)]) == 1
    assert validate_lineage.main(["--root", str(tmp_path)]) == 1


def test_error_messages_carry_field_path(capsys):
    validate_schema.main(["--root", str(FIXTURES / "broken" / "schema_bad_logical_type")])
    assert "schema[0].properties[2].logicalType" in capsys.readouterr().out


def test_repository_contracts_pass_schema_and_lineage():
    """Les vrais contrats du depot (verifie aussi le contrat temoin)."""
    assert schema_errors(REPO_ROOT) == []
    assert validate_lineage.run(REPO_ROOT, count=False) == []


def _columns(contract_id: str) -> dict:
    path = next((REPO_ROOT / "contracts").rglob(f"{contract_id}.odcs.yaml"))
    return {p["name"]: p for p in load_yaml(path)["schema"][0]["properties"]}


def test_repository_hashed_key_expression_names_a_published_column():
    key = _columns("core__customers")["customer_key"]
    assert key["customProperties"][0]["value"] == "customer_key"


def test_repository_ga4_event_id_is_pseudonymized():
    event_id = _columns("core__web_events")["event_id"]
    assert event_id["classification"] == "C2" and "pseudonymized" in event_id["tags"]


def test_repository_lineage_lists_columns_that_filter_rows():
    def sources(contract_id, column):
        return {s.split(".", 1)[1] for s in _columns(contract_id)[column]["transformSourceObjects"]}

    assert {"user_pseudo_id", "event_type", "is_analytics_consented", "web_order_id", "source_system"} <= sources("audiences", "customer_key")
    for column in ("channel", "month_date"):
        assert {"first_web_order_at", "customer_key", "event_type", "source_system"} <= sources("acquisition_monthly", column)
