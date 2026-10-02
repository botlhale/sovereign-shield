"""Apply the Triple-Lock policy plane through a SQL warehouse in an existing estate.

Runs the same content-addressed DDL, definition checks and binding verification as
the Asset Bundle task, using the operator's Azure CLI identity instead of Spark.
Writes the functions, tables and views it found or created to a JSON result file,
also when a later statement fails, so partial creations keep teardown ownership.
"""

import argparse
import json
import os
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
    args = parser.parse_args()
    if args.skip_grants:
        os.environ["SOVEREIGNSHIELD_SKIP_GRANTS"] = "1"
    with connect(args.host.removeprefix("https://").rstrip("/"), args.warehouse_id) as connection:
        session = WarehouseSession(connection)
        before = inventory(session)
        try:
            apply_security.apply_security_layer(spark=session)
        finally:
            result = [{"kind": kind, "name": name, "pre_existing": (kind, name) in before}
                      for kind, name in sorted(inventory(session))]
            args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Recorded {len(result)} policy-plane objects ({sum(not item['pre_existing'] for item in result)} created).")


if __name__ == "__main__":
    main()
