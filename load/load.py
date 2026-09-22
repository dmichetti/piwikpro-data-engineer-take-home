"""
Raw-layer load: copy the two HR/PM Excel exports into DuckDB, untouched.


The only transformations applied are structural: locating the header and
"Generated"/"Report Date" rows by content rather than fixed position, and
renaming headers to their final column names per the specs below. Any header
missing from, or not in, a spec fails the load, so a source layout change fails
loudly instead of silently misparsing.
"""

import logging
import os
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
# Overridable so each dbt target (dev/test/prod) can load into its own file;
# relative values resolve against the repo root, like profiles.yml's paths.
DUCKDB_PATH = REPO_ROOT / os.environ.get("DUCKDB_PATH", "warehouse.duckdb")

# Structural rows are always near the top; bounding the search avoids ever
# mistaking a data row for one of them.
STRUCTURAL_SEARCH_ROWS = 10

GENERATED_DATE_LABEL_PATTERN = re.compile(r"generated|report date", re.IGNORECASE)
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}")

# --- dlt column type hints -------------------------------------------------
def _text() -> dict[str, Any]:
    return {"data_type": "text"}


def _date() -> dict[str, Any]:
    return {"data_type": "date"}


# One spec per source file: {source header: (final column name, dlt type hint)}.
# It is the contract with the file - the load fails if the headers found differ
# from these - and the single source for renames and dlt column hints. The first
# entry doubles as the anchor used to locate the header row.
EMPLOYEE_SPEC = {
    "Employee ID": ("employee_id", _text()),
    "First Name": ("first_name", _text()),
    "Last Name": ("last_name", _text()),
    "Email Address": ("email_address", _text()),
    "Department": ("department", _text()),
    "Job Title": ("job_title", _text()),
    "Date of Hire": ("date_of_hire", _date()),
    "Termination Date": ("termination_date", _date()),
    "Status": ("status", _text()),
    "Reports To": ("reports_to", _text()),
}

ASSIGNMENT_SPEC = {
    "Assignment ID": ("assignment_id", _text()),
    "Emp. ID": ("emp_id", _text()),
    "Project Code": ("project_code", _text()),
    "Project Name": ("project_name", _text()),
    "Assignment Role": ("assignment_role", _text()),
    "Start Date": ("start_date", _date()),
    "Weekly Hours": ("weekly_hours", {"data_type": "bigint"}),
    "Billable?": ("billable", _text()),
}

# Added by the loader, not present in the file, so never part of the header check.
LOADER_COLUMNS = {"source_generated_at": _text()}


def _dlt_columns(spec: dict[str, tuple[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    return {name: hint for name, hint in spec.values()} | LOADER_COLUMNS


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


def _validate_headers(
    headers: list[Any], spec: dict[str, tuple[str, dict[str, Any]]], filename: str
) -> None:
    """Fail loudly on any missing, unexpected or duplicated header."""
    missing = sorted(map(str, set(spec) - set(headers)))
    unexpected = sorted(map(str, set(headers) - set(spec)))
    has_duplicates = len(headers) != len(set(headers))
    if missing or unexpected or has_duplicates:
        raise ValueError(
            f"Header mismatch in {filename} - the source layout may have changed. "
            f"Missing: {missing}; unexpected: {unexpected}; duplicates: {has_duplicates}."
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

def read_excel_raw(
    filename: str, sheet_name: str, spec: dict[str, tuple[str, dict[str, Any]]]
) -> list[dict[str, Any]]:
    header_anchor = next(iter(spec))
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

    headers = list(raw.iloc[header_row])
    _validate_headers(headers, spec, filename)

    df = raw.iloc[header_row + 1 :].copy()

    # Rename explicitly rather than leaving it to dlt's normalizer
    df.columns = headers
    df = df.rename(columns={source: name for source, (name, _) in spec.items()})

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
    columns=_dlt_columns(EMPLOYEE_SPEC),
)
def hr_employees_export() -> Iterator[list[dict[str, Any]]]:
    yield read_excel_raw("hr_employees_export.xlsx", "Employee Master Data", EMPLOYEE_SPEC)


@dlt.resource(
    name="project_assignments_report",
    write_disposition="replace",
    columns=_dlt_columns(ASSIGNMENT_SPEC),
)
def project_assignments_report() -> Iterator[list[dict[str, Any]]]:
    yield read_excel_raw(
        "project_assignments_report.xlsx", "Project Assignments", ASSIGNMENT_SPEC
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
