from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import apply_security


def test_policy_binding_failure_cannot_report_success(tmp_path, monkeypatch, capsys):
    script = tmp_path / "policy.sql"
    script.write_text(
        "-- @tolerate-failure\n"
        "ALTER TABLE agg_sdmx_history SET ROW FILTER fn_rls_multi_persona_lock "
        "ON (TIME_SERIES_CODE, BATCH_STATUS, OBS_CONF);\n",
        encoding="utf-8",
    )

    def reject_binding(statement):
        raise RuntimeError("Synthetic binding failure")

    session = SimpleNamespace(sql=reject_binding)
    monkeypatch.setattr(
        apply_security, "SparkSession",
        SimpleNamespace(builder=SimpleNamespace(getOrCreate=lambda: session)),
    )
    monkeypatch.setenv("SOVEREIGNSHIELD_SKIP_GRANTS", "1")

    with pytest.raises(RuntimeError, match="Synthetic binding failure"):
        apply_security.apply_security_layer(str(script))

    assert "established successfully" not in capsys.readouterr().out


def test_normal_policy_deployment_never_detaches_protection():
    sql_path = Path(apply_security.resolve_sql_path())
    statements = apply_security.parse_statements(sql_path.read_text(encoding="utf-8"))

    for statement, _ in statements:
        assert "DROP ROW FILTER" not in statement.upper()
        assert "DROP MASK" not in statement.upper()


def test_policy_names_are_content_addressed_and_never_replaced():
    original = "CREATE OR REPLACE FUNCTION mask(value DOUBLE) RETURNS DOUBLE RETURN NULL"
    compiled, versions = apply_security.version_policy_functions([original])
    repeated, same_versions = apply_security.version_policy_functions([original])
    _, changed_versions = apply_security.version_policy_functions([original + " + 1"])

    assert compiled == repeated
    assert versions == same_versions
    assert versions != changed_versions
    assert compiled[0].startswith("CREATE FUNCTION IF NOT EXISTS mask__")
    assert "OR REPLACE" not in compiled[0]


@pytest.mark.parametrize("definition", [None, "RETURN value", "RETURN TRUE"])
def test_unexpected_existing_policy_definition_aborts(definition):
    session = SimpleNamespace(sql=lambda statement: SimpleNamespace(
        collect=lambda: [{"routine_definition": definition}]
    ))
    with pytest.raises(RuntimeError, match="Policy definition does not match"):
        apply_security.verify_policy_functions(session, [
            "CREATE FUNCTION IF NOT EXISTS mask__123(value DOUBLE) RETURNS DOUBLE RETURN NULL"
        ])


def test_missing_binding_aborts():
    session = SimpleNamespace(sql=lambda statement: SimpleNamespace(collect=lambda: []))
    with pytest.raises(RuntimeError, match="Expected exactly one filter binding"):
        apply_security.verify_policy_bindings(session, {})


@pytest.mark.parametrize("wrong_field", [None, "function", "columns"])
def test_current_runtime_metadata_preserves_strict_binding_checks(wrong_field):
    versions = {name: name + "__verified" for name in ("fn_rls_multi_persona_lock", "fn_ddm_obs_conf_mask", "fn_rls_micro_country_lock")}

    def query(statement):
        micro = "lbs_micro_transactions" in statement
        mask = "column_masks" in statement
        schema = "sovereign_intake" if micro else "sovereign_shield"
        kind = "mask" if mask else "filter"
        function = "fn_rls_micro_country_lock" if micro else "fn_ddm_obs_conf_mask" if mask else "fn_rls_multi_persona_lock"
        arguments = "reporting_country" if micro else "OBS_CONF,TIME_SERIES_CODE" if mask else "TIME_SERIES_CODE, BATCH_STATUS, OBS_CONF"
        row = {"table_catalog": "dbw_sovereignshield", "table_schema": schema,
               f"{kind}_name": f"dbw_sovereignshield.{schema}.{versions[function]}",
               "using_columns" if mask else "target_columns": arguments}
        if wrong_field == "function":
            row[f"{kind}_name"] = "other.schema.function"
        if wrong_field == "columns":
            row["using_columns" if mask else "target_columns"] = "WRONG_COLUMN"
        return SimpleNamespace(collect=lambda: [SimpleNamespace(asDict=lambda: row)])

    session = SimpleNamespace(sql=query)
    if wrong_field:
        with pytest.raises(RuntimeError, match="Unexpected"):
            apply_security.verify_policy_bindings(session, versions)
    else:
        apply_security.verify_policy_bindings(session, versions)


@pytest.mark.parametrize("classification", [None, "", "UNRECOGNIZED", "C", "N"])
def test_unrecognized_classification_is_masked_for_researchers(classification):
    from uc_query import LocalDeltaBackend, Principal

    frame = pd.DataFrame([{
        "TIME_SERIES_CODE": "Q.S.C.A.USD.F.5J.A.CA.A.5J",
        "BATCH_STATUS": "PUBLISHED", "OBS_CONF": classification, "OBS_VALUE": 123.0,
    }])
    principal = Principal(
        display_name="researcher", authenticated=True,
        groups=frozenset({"sg-sovereignshield-researchers"}),
    )
    result = LocalDeltaBackend._apply_persona(frame, principal)
    assert len(result) == 1
    assert result["OBS_VALUE"].isna().all()