"""Raw-layer load: copy the two HR/PM Excel exports into DuckDB, untouched.

No data-quality cleanup happens here on purpose — this is the raw layer.
Cleaning (e.g. Billable? Y/Yes/N/No, ambiguous project leads, ...) is a dbt
staging concern, done later where it's visible and testable.

The only transformation applied is structural: locating the header and
"Generated"/"Report Date" rows by content rather than fixed position, so a
source layout change fails loudly instead of silently misparsing.
"""

import logging
import re
from pathlib import Path
from typing import Any, Callable, Iterator

import dlt
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# --- Paths & constants ---------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DUCKDB_PATH = REPO_ROOT / "warehouse.duckdb"

# Structural rows are always near the top; bounding the search avoids ever
# mistaking a data row for one of them.
STRUCTURAL_SEARCH_ROWS = 10

GENERATED_DATE_LABEL_PATTERN = re.compile(r"generated|report date", re.IGNORECASE)
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}")

# --- dlt column type hints -------------------------------------------------
def _text() -> dict[str, Any]:
    return {"data_type": "text"}


def _date() -> dict[str, Any]:
    # pandas has no date-only dtype - Excel dates always arrive as
    # datetime64/Timestamp with an implicit 00:00:00 time we don't want.
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

# --- Structural row detection ----------------------------------------------

def _find_row(
    first_column: "pd.Series[Any]",
    matches: Callable[[str], bool],
    description: str,
    filename: str,
) -> int:
    """Locate a structural row by content instead of a fixed position."""
    for row_index, value in first_column.head(STRUCTURAL_SEARCH_ROWS).items():
        if matches(str(value)):
            return row_index
    raise ValueError(
        f"Could not find {description} in the first {STRUCTURAL_SEARCH_ROWS} "
        f"rows of {filename} - the source layout may have changed."
    )


def _extract_source_generated_at(raw_cell: Any, filename: str) -> str:
    """Pull the date out of a 'Generated: 2026-02-02' / 'Report Date: 02/02/2026' cell."""
    match = DATE_PATTERN.search(str(raw_cell))
    if not match:
        raise ValueError(
            f"Found a 'Generated'/'Report Date' row in {filename} but "
            f"couldn't parse a date out of it: {raw_cell!r}"
        )
    return match.group(0)


# --- Extraction --------------------------------------------------------

def read_excel_raw(filename: str, sheet_name: str, header_anchor: str) -> list[dict[str, Any]]:
    raw = pd.read_excel(DATA_DIR / filename, sheet_name=sheet_name, header=None)
    first_column = raw.iloc[:, 0]

    generated_date_row = _find_row(
        first_column,
        lambda value: GENERATED_DATE_LABEL_PATTERN.search(value) is not None,
        "a 'Generated'/'Report Date' row",
        filename,
    )
    header_row = _find_row(
        first_column,
        lambda value: value == header_anchor,
        f"a header row starting with {header_anchor!r}",
        filename,
    )

    source_generated_at = _extract_source_generated_at(raw.iat[generated_date_row, 0], filename)

    df = raw.iloc[header_row + 1 :].copy()

    # Strip trailing "?" (e.g. "Billable?"): dlt can't cleanly drop it on its
    # own and mangles the column name instead (e.g. into "billablex").
    df.columns = raw.iloc[header_row].str.rstrip("?")

    # Drop rows null across every column - a trailing-blank-row artifact of
    # Excel exports, not a data value. A partially-incomplete row stays as-is.
    row_count_before_dropna = len(df)
    df = df.dropna(how="all")
    dropped_row_count = row_count_before_dropna - len(df)
    if dropped_row_count:
        logger.info("Dropped %d fully-empty row(s) from %s", dropped_row_count, filename)

    df["source_generated_at"] = source_generated_at

    logger.info("Read %d rows from %s (sheet '%s')", len(df), filename, sheet_name)
    return df.to_dict(orient="records")


# --- dlt resources -----------------------------------------------------


@dlt.resource(
    name="hr_employees_export",
    write_disposition="replace",  # full snapshot each run, not incremental
    columns=EMPLOYEE_COLUMNS,
)
def hr_employees_export() -> Iterator[list[dict[str, Any]]]:
    yield read_excel_raw(
        "hr_employees_export.xlsx", "Employee Master Data", header_anchor="Employee ID"
    )


@dlt.resource(
    name="project_assignments_report",
    write_disposition="replace",
    columns=ASSIGNMENT_COLUMNS,
)
def project_assignments_report() -> Iterator[list[dict[str, Any]]]:
    yield read_excel_raw(
        "project_assignments_report.xlsx", "Project Assignments", header_anchor="Assignment ID"
    )


# --- Entry point ---------------------------------------------------------


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
