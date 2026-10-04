"""Apply the Triple-Lock policy plane through a SQL warehouse in an existing estate.

Runs the same content-addressed DDL, definition checks and binding verification as
the Asset Bundle task, using the operator's Azure CLI identity instead of Spark.
Writes the functions, tables and views the policy DDL defines that it found or
created to a JSON result file, also when a later statement fails, so partial
creations keep teardown ownership; unrelated objects in the shared schemas are ignored.
Refuses to rebind or replace an existing table or view it did not create unless
adoption is explicit, because those changes are not reversed at teardown.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import apply_security  # noqa: E402

CATALOG = "dbw_sovereignshield"
SCHEMAS = ("sovereign_shield", "sovereign_intake")


class WarehouseSession:
    """The subset of a SparkSession that apply_security uses, over Databricks SQL."""

    def __init__(self, connection):
        self._cursor = connection.cursor()
        self.catalog = SimpleNamespace(tableExists=self._table_exists)

    def sql(self, statement, parameters=None):
        self._cursor.execute(statement, parameters)
        rows = self._cursor.fetchall() if self._cursor.description else []
        return SimpleNamespace(collect=lambda: rows)

    def _table_exists(self, name):
        catalog, schema, table = name.split(".")
        return bool(self.sql(
            f"SELECT 1 FROM {catalog}.information_schema.tables WHERE table_schema = :schema AND table_name = :name",
            {"schema": schema, "name": table},
        ).collect())


def inventory(session):
    schemas = ", ".join(f"'{schema}'" for schema in SCHEMAS)
    objects = {("function", f"{CATALOG}.{row[0]}.{row[1]}") for row in session.sql(
        f"SELECT routine_schema, routine_name FROM {CATALOG}.information_schema.routines "
        f"WHERE routine_schema IN ({schemas})").collect()}
    objects |= {("view" if row[2] == "VIEW" else "table", f"{CATALOG}.{row[0]}.{row[1]}") for row in session.sql(
        f"SELECT table_schema, table_name, table_type FROM {CATALOG}.information_schema.tables "
        f"WHERE table_schema IN ({schemas})").collect()}
    return objects


def policy_statements():
    with open(apply_security.resolve_sql_path(), encoding="utf-8") as source:
        return [statement for statement, _ in apply_security.parse_statements(source.read())]


def qualify(name):
    parts = name.split(".")
    return ".".join({1: [CATALOG, SCHEMAS[0]], 2: [CATALOG], 3: []}[len(parts)] + parts)


def modified_objects():
    """Tables and views whose bindings or definitions the policy SQL replaces."""
    objects = set()
    for statement in policy_statements():
        match = re.match(r"(ALTER TABLE|CREATE OR REPLACE VIEW)\s+([\w.]+)", statement, re.I)
        if match:
            objects.add(qualify(match.group(2)))
    return objects


def policy_objects():
    """Functions, tables and views the policy SQL can create, with content-addressed function names."""
    statements, _ = apply_security.version_policy_functions(policy_statements())
    kinds = {"CREATE FUNCTION IF NOT EXISTS": "function", "CREATE TABLE IF NOT EXISTS": "table",
             "CREATE OR REPLACE VIEW": "view"}
    objects = set()
    for statement in statements:
        match = re.match(r"(CREATE FUNCTION IF NOT EXISTS|CREATE TABLE IF NOT EXISTS|CREATE OR REPLACE VIEW)"
                         r"\s+([\w.]+)", statement, re.I)
        if match:
            objects.add((kinds[re.sub(r"\s+", " ", match.group(1)).upper()], qualify(match.group(2))))
    return objects


def connect(host, warehouse_id):
    from databricks import sql
    from databricks.sdk.core import Config

    headers = Config(host=f"https://{host}", auth_type="azure-cli").authenticate()
    token = headers["Authorization"].split(" ", 1)[1]
    return sql.connect(server_hostname=host, http_path=f"/sql/1.0/warehouses/{warehouse_id}", access_token=token)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="workspace host without https://")
    parser.add_argument("--warehouse-id", required=True)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--skip-grants", action="store_true")
    parser.add_argument("--owned", action="append", default=[], metavar="NAME",
                        help="object a previous run created; repeat for each")
    parser.add_argument("--adopt-existing", action="store_true",
                        help="rebind and replace existing tables and views this tool did not create")
    args = parser.parse_args()
    if args.skip_grants:
        os.environ["SOVEREIGNSHIELD_SKIP_GRANTS"] = "1"
    with connect(args.host.removeprefix("https://").rstrip("/"), args.warehouse_id) as connection:
        session = WarehouseSession(connection)
        candidates = policy_objects()
        before = inventory(session)
        existing = {name for _, name in before}
        foreign = sorted(modified_objects() & existing - set(args.owned))
        if foreign and not args.adopt_existing:
            args.result.write_text("[]\n", encoding="utf-8")
            sys.exit("Refusing to rebind or replace existing objects this tool did not create: "
                     f"{', '.join(foreign)}. Teardown would not restore them; rerun with --adopt-existing "
                     "to accept the change.")
        try:
            apply_security.apply_security_layer(spark=session)
        finally:
            result = [{"kind": kind, "name": name, "pre_existing": (kind, name) in before}
                      for kind, name in sorted(inventory(session) & candidates)]
            args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Recorded {len(result)} policy-plane objects ({sum(not item['pre_existing'] for item in result)} created).")


if __name__ == "__main__":
    main()
