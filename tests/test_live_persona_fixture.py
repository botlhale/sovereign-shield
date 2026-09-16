import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sh"))
spec = importlib.util.spec_from_file_location("live_persona_checks", ROOT / "sh/live_persona_checks.py")
verification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verification)


def test_live_persona_assertions_reject_unaffiliated_leak(corpus):
    with pytest.raises(AssertionError, match="Unaffiliated"):
        verification.assert_persona("unaffiliated", corpus)
    verification.assert_persona("unaffiliated", corpus.iloc[:0])


def test_live_public_assertions_are_not_vacuous(corpus):
    with pytest.raises(AssertionError):
        verification.assert_persona("public", corpus)
    with pytest.raises(AssertionError, match="no fixture rows"):
        verification.assert_persona("public", corpus.iloc[:0])