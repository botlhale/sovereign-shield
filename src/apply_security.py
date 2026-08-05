"""Applies the SovereignShield Triple-Lock security architecture to Unity Catalog.

Executes `unity_catalog_triple_lock.sql` statement by statement. Statements
preceded by a `-- @tolerate-failure` marker are expected to fail on one of the
two lifecycle paths (fresh create vs. re-apply) and are logged and skipped;
every other failure aborts the deployment so the platform is never left in a
partially secured state.
"""

import inspect
import os
import re
import sys

from pyspark.sql import SparkSession

#: Marker comment declaring that the following statement may fail harmlessly.
TOLERATE_MARKER = "@tolerate-failure"

#: DDL script deployed alongside this module.
SQL_FILENAME = "unity_catalog_triple_lock.sql"


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


def apply_security_layer(sql_path: str | None = None) -> None:
    spark = SparkSession.builder.getOrCreate()

    sql_path = sql_path or resolve_sql_path()
    print(f"Reading SQL architecture from: {sql_path}")
    with open(sql_path, "r", encoding="utf-8") as file:
        sql_content = file.read()

    statements = parse_statements(sql_content)
    print(f"Parsed {len(statements)} statement(s).")

    skipped = 0
    for index, (statement, tolerate) in enumerate(statements, start=1):
        label = re.sub(r"\s+", " ", statement)[:70]
        try:
            spark.sql(statement)
            print(f"  [{index}/{len(statements)}] OK      {label}")
        except Exception as exc:
            if not tolerate:
                print(f"  [{index}/{len(statements)}] FAILED  {label}")
                raise
            skipped += 1
            print(f"  [{index}/{len(statements)}] SKIPPED {label} -> {type(exc).__name__}")

    print(f"Zero-Trust Security Layer established successfully ({skipped} tolerated no-op(s)).")


if __name__ == "__main__":
    apply_security_layer()