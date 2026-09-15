"""Deploy immutable policy functions and verify bindings without dropping protection."""

import hashlib
import inspect
import os
import re
import sys

from pyspark.sql import SparkSession

#: Marker comment declaring that the following statement may fail harmlessly.
TOLERATE_MARKER = "@tolerate-failure"

#: Data and policy plane - always applied.
SQL_FILENAME = "unity_catalog_triple_lock.sql"

#: Access-control plane - skippable when Terraform owns it.
GRANTS_FILENAME = "unity_catalog_grants.sql"


def _candidate_directories() -> list[str]:
    """Directories that may contain the DDL script, in priority order.

    Databricks runs a spark_python_task via ``exec(compile(source, filename, 'exec'))``,
    so ``__file__`` is undefined and the working directory is not the bundle root. The
    compiled code object still carries the real path, which the current frame exposes.
    """
    directories = []

    module_file = globals().get("__file__")
    if module_file:
        directories.append(os.path.dirname(os.path.abspath(module_file)))

    frame = inspect.currentframe()
    if frame is not None:
        code_path = frame.f_code.co_filename
        if code_path and os.path.sep in code_path:
            directories.append(os.path.dirname(os.path.abspath(code_path)))

    if sys.argv and sys.argv[0]:
        directories.append(os.path.dirname(os.path.abspath(sys.argv[0])))

    cwd = os.getcwd()
    directories.extend([os.path.join(cwd, "src"), cwd])

    seen = set()
    return [d for d in directories if d and not (d in seen or seen.add(d))]


def resolve_sql_path(filename: str = SQL_FILENAME) -> str:
    """Locates the DDL script across the local, bundle, and notebook layouts."""
    searched = []
    for directory in _candidate_directories():
        candidate = os.path.join(directory, filename)
        searched.append(candidate)
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError(
        f"Could not locate {filename}. Searched:\n  " + "\n  ".join(searched)
    )


def parse_statements(sql_content: str):
    """Splits a SQL script into (statement, tolerate_failure) pairs.

    Line comments are stripped before splitting so that a `;` inside a comment
    cannot truncate the statement that follows it.
    """
    statements = []
    buffer: list[str] = []
    tolerate = False

    for raw_line in sql_content.splitlines():
        comment = raw_line.split("--", 1)[1] if "--" in raw_line else ""
        # Exact match only, so prose mentioning the marker cannot arm it.
        if comment.strip() == TOLERATE_MARKER and not buffer:
            tolerate = True
        line = raw_line.split("--", 1)[0]
        if not line.strip():
            continue
        buffer.append(line)
        if line.rstrip().endswith(";"):
            statement = "\n".join(buffer).strip().rstrip(";").strip()
            if statement:
                statements.append((statement, tolerate))
            buffer, tolerate = [], False

    trailing = "\n".join(buffer).strip().rstrip(";").strip()
    if trailing:
        statements.append((trailing, tolerate))

    return statements


def version_policy_functions(statements: list[str]) -> tuple[list[str], dict[str, str]]:
    versions = {}
    for statement in statements:
        match = re.match(r"CREATE OR REPLACE FUNCTION ([\w.]+)\(", statement, re.I)
        if match:
            name = match.group(1).split(".")[-1]
            digest = hashlib.sha256(statement.encode("utf-8")).hexdigest()[:16]
            versions[name] = f"{name}__{digest}"
    return [replace_policy_names(statement, versions).replace(
        "CREATE OR REPLACE FUNCTION", "CREATE FUNCTION IF NOT EXISTS"
    ) for statement in statements], versions


def replace_policy_names(statement: str, versions: dict[str, str]) -> str:
    for original, versioned in versions.items():
        statement = re.sub(rf"\b{re.escape(original)}\b", versioned, statement)
    return statement


def verify_policy_functions(spark, statements: list[str]) -> None:
    for statement in statements:
        match = re.match(r"CREATE FUNCTION IF NOT EXISTS ([\w.]+)\(", statement)
        if not match:
            continue
        qualified = match.group(1).split(".")
        schema = qualified[-2] if len(qualified) > 1 else "sovereign_shield"
        name = qualified[-1]
        rows = spark.sql(
            "SELECT routine_definition FROM dbw_sovereignshield.information_schema.routines "
            f"WHERE routine_schema = '{schema}' AND routine_name = '{name}'"
        ).collect()
        expected = re.split(r"\bRETURN\b", statement, maxsplit=1)[1]

        def normalize(expression):
            expression = re.sub(r"^\s*RETURN\b", "", expression or "", flags=re.I)
            return re.sub(r"\s+", " ", expression).strip().rstrip(";")

        if len(rows) != 1 or normalize(rows[0]["routine_definition"]) != normalize(expected):
            raise RuntimeError(f"Policy definition does not match the release: {schema}.{name}.")


def verify_existing_table_contracts(spark) -> None:
    required = {"SUBMISSION_ID", "SOURCE_SHA256", "RECORD_ID", "SUBMITTED_AT", "RECEIVED_AT", "BATCH_FAILED_RULE_ID", "VALIDATION_NOTES"}
    for schema, table, measure in (
        ("sovereign_shield", "agg_sdmx_history", "OBS_VALUE"),
        ("sovereign_intake", "lbs_micro_transactions", "transaction_amount"),
    ):
        qualified = f"dbw_sovereignshield.{schema}.{table}"
        if not spark.catalog.tableExists(qualified):
            continue
        rows = spark.sql(
            "SELECT column_name, data_type, numeric_precision, numeric_scale "
            "FROM dbw_sovereignshield.information_schema.columns "
            f"WHERE table_schema = '{schema}' AND table_name = '{table}'"
        ).collect()
        columns = {row["column_name"].upper(): row for row in rows}
        value = columns.get(measure.upper())
        if value is None or value["data_type"] != "DECIMAL" or value["numeric_precision"] != 38 or value["numeric_scale"] != 3:
            raise RuntimeError(f"{qualified} requires an explicit DECIMAL(38,3) migration; existing policies were not changed.")
        if table == "agg_sdmx_history" and required - set(columns):
            raise RuntimeError(f"{qualified} requires the explicit submission-history migration; existing policies were not changed.")


def verify_policy_bindings(spark, versions: dict[str, str]) -> None:
    expected = (
        ("row_filters", "sovereign_shield", "agg_sdmx_history", "filter", "fn_rls_multi_persona_lock", "TIME_SERIES_CODE,BATCH_STATUS,OBS_CONF", ""),
        ("column_masks", "sovereign_shield", "agg_sdmx_history", "mask", "fn_ddm_obs_conf_mask", "OBS_CONF,TIME_SERIES_CODE", "AND column_name = 'OBS_VALUE'"),
        ("row_filters", "sovereign_intake", "lbs_micro_transactions", "filter", "fn_rls_micro_country_lock", "reporting_country", ""),
    )
    for relation, schema, table, kind, function, columns, extra in expected:
        rows = spark.sql(
            f"SELECT {kind}_catalog AS catalog, {kind}_schema AS schema, "
            f"{kind}_name AS name, {kind}_col_usage AS columns "
            f"FROM dbw_sovereignshield.information_schema.{relation} "
            f"WHERE catalog_name = 'dbw_sovereignshield' "
            f"AND schema_name = '{schema}' AND table_name = '{table}' {extra}"
        ).collect()
        if len(rows) != 1:
            raise RuntimeError(f"Expected exactly one {kind} binding on {schema}.{table}.")
        binding = rows[0].asDict()
        actual_columns = re.sub(r"[\s`]", "", binding["columns"] or "").upper()
        if (binding["catalog"] != "dbw_sovereignshield" or binding["schema"] != schema
                or binding["name"] != versions[function] or actual_columns != columns.upper()):
            raise RuntimeError(f"Unexpected {kind} binding on {schema}.{table}.")


def apply_security_layer(sql_path: str | None = None) -> None:
    spark = SparkSession.builder.getOrCreate()
    with open(sql_path or resolve_sql_path(), encoding="utf-8") as source:
        statements, versions = version_policy_functions([
            statement for statement, _ in parse_statements(source.read())
        ])
    with open(resolve_sql_path(GRANTS_FILENAME), encoding="utf-8") as source:
        grants = [replace_policy_names(statement, versions)
                  for statement, _ in parse_statements(source.read())]

    def execute(statement):
        label = re.sub(r"\s+", " ", statement)[:90]
        spark.sql(statement)
        print(f"OK {label}")

    boundary = next((index for index, statement in enumerate(statements)
                     if statement.startswith("CREATE TABLE")), len(statements))
    if versions:
        verify_existing_table_contracts(spark)
    for statement in statements[:boundary]:
        execute(statement)
    if versions:
        verify_policy_functions(spark, statements)
    for statement in statements[boundary:]:
        execute(statement)
    if versions:
        verify_policy_bindings(spark, versions)
    if os.getenv("SOVEREIGNSHIELD_SKIP_GRANTS", "").lower() not in ("1", "true"):
        for grant in grants:
            execute(grant)
    print("Security policies established and bindings verified successfully.")


if __name__ == "__main__":
    apply_security_layer()