{#-
    Every project with at least one assignment record must appear in
    project_staffing, regardless of whether any of its employees are active.
    This directly validates the business rule that a project with zero
    active employees must still appear in the output.
-#}

select project_code
from {{ ref('stg_employee_assignements') }}

except

select project_code
from {{ ref('project_staffing') }}
