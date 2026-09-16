import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("configure_bundle", ROOT / "sh/configure_bundle.py")
bundle_config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle_config)


def test_complex_override_is_an_object_and_preserves_unrelated_values(tmp_path):
    cluster = {"policy_id": "policy", "num_workers": 0, "apply_policy_default_values": True}
    path = bundle_config.write_overrides(tmp_path, "dev", cluster, "service-principal", "warehouse")
    values = json.loads(path.read_text(encoding="utf-8"))
    values["catalog"] = "preserved"
    path.write_text(json.dumps(values), encoding="utf-8")
    bundle_config.write_overrides(tmp_path, "dev", cluster, "service-principal", "warehouse")
    values = json.loads(path.read_text(encoding="utf-8"))
    assert values["ingestion_cluster"] == cluster
    assert values["catalog"] == "preserved"
    assert path == tmp_path / ".databricks/bundle/dev/variable-overrides.json"
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_string_encoded_complex_override_is_refused(tmp_path):
    with pytest.raises(ValueError, match="governed cluster object"):
        bundle_config.write_overrides(tmp_path, "dev", '{"policy_id":"policy"}', "principal", "warehouse")


def test_ci_does_not_set_unsupported_complex_environment_variable():
    workflow = (ROOT / ".github/workflows/promote.yml").read_text(encoding="utf-8")
    assert "BUNDLE_VAR_ingestion_cluster:" not in workflow
    assert "configure_bundle.py --target dev --from-environment" in workflow


def test_portal_container_includes_new_runtime_dependencies_and_assets():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for source in ("src/decimal_measures.py", "src/lbs_contract.py", "src/reference_data/lbs_structure.json", "src/static"):
        assert source in dockerfile
        assert (ROOT / source).exists()
    assert "COPY src/ ./" not in dockerfile