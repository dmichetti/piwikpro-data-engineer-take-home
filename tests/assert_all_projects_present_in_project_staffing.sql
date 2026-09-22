{#- Every project with at least one assignment record must appear in
    project_staffing, regardless of whether any of its employees are active
    - this directly validates that business rule. Compared against
    stg_employee_assignements (not int_employee_assignements) on purpose: if
    int_employee_assignements' LEFT JOIN ever became an INNER JOIN, it would
    already be missing the same rows, and a comparison against it would pass
    despite the regression.

    warn_if/error_if, same pattern as the multi-lead test: one dropped
    project is worth a warning; more than two would be a systemic pipeline
    failure, not a one-off, and should fail the build. #}
{{ config(warn_if='>0', error_if='>2') }}

select project_code
from {{ ref('stg_employee_assignements') }}

except

select project_code
from {{ ref('project_staffing') }}
