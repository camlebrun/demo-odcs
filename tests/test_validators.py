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
from common import REPO_ROOT

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
    expected = {f"L{n:03d}" for n in range(1, 17)} | {"SCHEMA"}
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
