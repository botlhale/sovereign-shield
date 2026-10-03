import re
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
        "ON (L_REP_CTY, BATCH_STATUS, OBS_CONF);\n",
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


def _reveal_branches(ddl, function, returned):
    body = ddl.split(f"FUNCTION {function}(", 1)[1].split("END;", 1)[0]
    return [re.sub(r"\s+", " ", branch) for branch in re.findall(rf"WHEN (.+?) THEN {returned}\b", body, re.S)]


def test_coordinate_and_lineage_masks_share_the_value_reveal_rule():
    """A key or hash must never be revealed to someone denied the value itself."""
    ddl = Path(apply_security.resolve_sql_path()).read_text(encoding="utf-8")
    expected = _reveal_branches(ddl, "fn_ddm_obs_conf_mask", "obs_val")

    assert len(expected) == 4
    assert _reveal_branches(ddl, "fn_ddm_series_key_mask", "time_series_code") == expected
    assert _reveal_branches(ddl, "fn_ddm_lineage_mask", "lineage") == expected


def test_withheld_rows_mask_coordinates_and_lineage_inline_and_on_rebind():
    ddl = Path(apply_security.resolve_sql_path()).read_text(encoding="utf-8")

    assert "TIME_SERIES_CODE STRING MASK fn_ddm_series_key_mask USING COLUMNS (OBS_CONF, L_REP_CTY)" in ddl
    assert "ALTER COLUMN TIME_SERIES_CODE SET MASK fn_ddm_series_key_mask USING COLUMNS (OBS_CONF, L_REP_CTY)" in ddl
    assert "concat(substring_index(time_series_code, '.', 9), '.xx.xx')" in ddl
    for column in ("RECORD_ID", "version_hash", "VALIDATION_NOTES"):
        assert f"{column} STRING MASK fn_ddm_lineage_mask USING COLUMNS (OBS_CONF, L_REP_CTY)" in ddl
        assert f"ALTER COLUMN {column} SET MASK fn_ddm_lineage_mask USING COLUMNS (OBS_CONF, L_REP_CTY)" in ddl


def test_masked_key_is_never_a_policy_input():
    """Unity Catalog rejects a masked column in another policy's USING COLUMNS or ON clause."""
    ddl = Path(apply_security.resolve_sql_path()).read_text(encoding="utf-8")
    bindings = re.findall(r"(?:USING COLUMNS|ROW FILTER \w+ ON) \(([^)]*)\)", ddl)
    masked = {name.upper() for name in re.findall(r"(\w+) (?:STRING|DECIMAL\(38,3\)) MASK", ddl)}

    assert "TIME_SERIES_CODE" in masked and "L_REP_CTY" not in masked
    assert len(bindings) >= 12
    for columns in bindings:
        assert not masked & {name.strip().upper() for name in columns.split(",")}, columns


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
    names = ("fn_rls_multi_persona_lock", "fn_ddm_obs_conf_mask", "fn_ddm_series_key_mask",
             "fn_ddm_lineage_mask", "fn_rls_micro_country_lock")
    versions = {name: name + "__verified" for name in names}
    masks = {
        "OBS_VALUE": ("fn_ddm_obs_conf_mask", "OBS_CONF,L_REP_CTY"),
        "TIME_SERIES_CODE": ("fn_ddm_series_key_mask", "OBS_CONF, L_REP_CTY"),
        "RECORD_ID": ("fn_ddm_lineage_mask", "OBS_CONF, L_REP_CTY"),
        "version_hash": ("fn_ddm_lineage_mask", "`OBS_CONF`,`L_REP_CTY`"),
        "VALIDATION_NOTES": ("fn_ddm_lineage_mask", "OBS_CONF,L_REP_CTY"),
    }

    def query(statement):
        micro = "lbs_micro_transactions" in statement
        mask = "column_masks" in statement
        schema = "sovereign_intake" if micro else "sovereign_shield"
        kind = "mask" if mask else "filter"
        if mask:
            function, arguments = masks[re.search(r"column_name = '(\w+)'", statement).group(1)]
        else:
            function = "fn_rls_micro_country_lock" if micro else "fn_rls_multi_persona_lock"
            arguments = "reporting_country" if micro else "L_REP_CTY, BATCH_STATUS, OBS_CONF"
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

class _AnchorSession:
    """Records DDL and reports the anchor constraint once it has been added."""

    def __init__(self, existing=None, reject_add=False, exists=True):
        self.statements = []
        self.constraint = existing
        self.reject_add = reject_add
        self.catalog = SimpleNamespace(tableExists=lambda name: exists)

    def sql(self, statement):
        self.statements.append(statement)
        if statement.startswith("SHOW TBLPROPERTIES"):
            rows = [{"key": "delta.minReaderVersion", "value": "3"}]
            if self.constraint is not None:
                rows.append({"key": f"delta.constraints.{apply_security.ANCHOR_CONSTRAINT}", "value": self.constraint})
            return SimpleNamespace(collect=lambda: rows)
        if "ADD CONSTRAINT" in statement:
            if self.reject_add:
                raise RuntimeError("DELTA_NEW_CHECK_CONSTRAINT_VIOLATION: 1 row violates the new constraint")
            self.constraint = re.search(r"CHECK \((.*)\)$", statement).group(1)
        return SimpleNamespace(collect=lambda: [])


def test_anchor_constraint_validates_existing_rows_before_any_rebinding(monkeypatch):
    """A stored row whose L_REP_CTY is not key segment 9 would reveal its key to the wrong submitter."""
    session = _AnchorSession()
    for name in ("verify_existing_table_contracts", "verify_policy_functions", "verify_policy_bindings"):
        monkeypatch.setattr(apply_security, name, lambda *args: None)
    monkeypatch.setenv("SOVEREIGNSHIELD_SKIP_GRANTS", "1")

    apply_security.apply_security_layer(spark=session)

    add = next(i for i, s in enumerate(session.statements) if "ADD CONSTRAINT" in s)
    first_ddl = next(i for i, s in enumerate(session.statements) if not s.startswith("SHOW"))
    assert add == first_ddl
    assert session.statements[add] == (
        "ALTER TABLE dbw_sovereignshield.sovereign_shield.agg_sdmx_history ADD CONSTRAINT "
        "l_rep_cty_is_key_segment_9 CHECK (L_REP_CTY <=> get(split(TIME_SERIES_CODE, '[.]'), 8))"
    )
    assert sum("ADD CONSTRAINT" in s for s in session.statements) == 1


def test_mismatched_existing_anchor_aborts_before_policies_change(monkeypatch):
    session = _AnchorSession(reject_add=True)
    monkeypatch.setattr(apply_security, "verify_existing_table_contracts", lambda *args: None)

    with pytest.raises(RuntimeError, match="not segment 9 of TIME_SERIES_CODE"):
        apply_security.apply_security_layer(spark=session)

    assert not [s for s in session.statements if not s.startswith("SHOW") and "ADD CONSTRAINT" not in s]


@pytest.mark.parametrize("existing", ["L_REP_CTY IS NOT NULL", "TRUE"])
def test_different_anchor_constraint_is_refused(existing):
    session = _AnchorSession(existing=existing)
    with pytest.raises(RuntimeError, match="lacks the expected"):
        apply_security.enforce_reporting_country_anchor(session)
    assert not any("ADD CONSTRAINT" in s for s in session.statements)


def test_existing_anchor_constraint_is_kept_and_verify_only_never_adds():
    present = _AnchorSession(existing="L_REP_CTY <=> get(split(TIME_SERIES_CODE, '[.]'), 8)")
    apply_security.enforce_reporting_country_anchor(present)
    assert not any("ADD CONSTRAINT" in s for s in present.statements)

    absent = _AnchorSession()
    with pytest.raises(RuntimeError, match="lacks the expected"):
        apply_security.enforce_reporting_country_anchor(absent, add=False)
    assert not any("ADD CONSTRAINT" in s for s in absent.statements)

    missing = _AnchorSession(exists=False)
    apply_security.enforce_reporting_country_anchor(missing)
    assert missing.statements == []
