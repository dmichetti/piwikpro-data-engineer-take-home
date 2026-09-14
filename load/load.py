"""Raw-layer load: copy the two HR/PM Excel exports into DuckDB, untouched.

No data-quality cleanup happens here on purpose — this is the raw layer.
Cleaning (e.g. Billable? Y/Yes/N/No, ambiguous project leads, ...) is a dbt
staging concern, done later where it's visible and testable.

The only transformation applied is structural: skipping the report's title
rows to find the real header, and pulling the "Generated"/"Report Date" row
out into a `source_generated_at` column on every row.
"""

import logging
import re
from pathlib import Path
from typing import Any, Iterator

import dlt
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DUCKDB_PATH = REPO_ROOT / "warehouse.duckdb"

# Both source files share the same layout: title, generated/report date, blank, header.
GENERATED_DATE_ROW = 1
HEADER_ROW = 3

DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}")

# dlt can't infer a type for a column that's still null in the first row it
# processes, and defers adding such columns to the schema until it hits a
# real value - appending them at the end instead of their source position.
# A *partial* data_type hint doesn't fix this either: dlt groups explicitly
# typed columns before inferred ones, so getting the source column order back
# requires declaring data_type for every column, not just the affected one.
# Each hint below must be its own dict literal, not a shared reference: dlt
# mutates the hint dict in place while building the schema, so columns
# sharing one object end up aliased onto each other.
def _text() -> dict[str, Any]:
    return {"data_type": "text"}


def _date() -> dict[str, Any]:
    # pandas has no date-only dtype, so pd.read_excel always hands these back
    # as datetime64/Timestamp with an implicit 00:00:00 time. The source
    # cells carry no time-of-day, so "date" is the accurate destination type.
    return {"data_type": "date"}


EMPLOYEE_COLUMNS = {
    "employee_id": _text(),
    "first_name": _text(),
    "last_name": _text(),
    "email_address": _text(),
    "department": _text(),
    "job_title": _text(),
    "date_of_hire": _date(),
    "termination_date": _date(),
    "status": _text(),
    "reports_to": _text(),
    "source_generated_at": _text(),
}

ASSIGNMENT_COLUMNS = {
    "assignment_id": _text(),
    "emp_id": _text(),
    "project_code": _text(),
    "project_name": _text(),
    "assignment_role": _text(),
    "start_date": _date(),
    "weekly_hours": {"data_type": "bigint"},
    "billable": _text(),
    "source_generated_at": _text(),
}


def _extract_source_generated_at(raw_cell: Any) -> str:
    """Pull the date out of a 'Generated: 2026-02-02' / 'Report Date: 02/02/2026' cell.

    Kept as the raw string exactly as it appears in the source (no format
    normalization) - this is the raw layer.
    """
    match = DATE_PATTERN.search(str(raw_cell))
    return match.group(0) if match else str(raw_cell)


def read_excel_raw(filename: str, sheet_name: str) -> list[dict[str, Any]]:
    raw = pd.read_excel(DATA_DIR / filename, sheet_name=sheet_name, header=None)
    source_generated_at = _extract_source_generated_at(raw.iat[GENERATED_DATE_ROW, 0])

    df = raw.iloc[HEADER_ROW + 1 :].copy()
    # Strip trailing "?" from header text (e.g. "Billable?") before dlt sees
    # it: dlt's naming convention can't cleanly drop a trailing special
    # character on its own and instead mangles it (e.g. into "billablex").
    # This is structural header parsing, not a value-level transformation.
    df.columns = raw.iloc[HEADER_ROW].str.rstrip("?")
    df["source_generated_at"] = source_generated_at

    logger.info("Read %d rows from %s (sheet '%s')", len(df), filename, sheet_name)
    return df.to_dict(orient="records")


# write_disposition="replace": both sources are full snapshots, not incremental
# feeds, so re-running the load should reproduce the same state rather than
# accumulate duplicate rows.
@dlt.resource(
    name="hr_employees_export",
    write_disposition="replace",
    columns=EMPLOYEE_COLUMNS,
)
def hr_employees_export() -> Iterator[list[dict[str, Any]]]:
    yield read_excel_raw("hr_employees_export.xlsx", "Employee Master Data")


@dlt.resource(
    name="project_assignments_report",
    write_disposition="replace",
    columns=ASSIGNMENT_COLUMNS,
)
def project_assignments_report() -> Iterator[list[dict[str, Any]]]:
    yield read_excel_raw("project_assignments_report.xlsx", "Project Assignments")


def main() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="piwikpro_raw_load",
        destination=dlt.destinations.duckdb(credentials=str(DUCKDB_PATH)),
        dataset_name="raw",
    )

    load_info = pipeline.run([hr_employees_export(), project_assignments_report()])
    logger.info(load_info)


if __name__ == "__main__":
    main()
