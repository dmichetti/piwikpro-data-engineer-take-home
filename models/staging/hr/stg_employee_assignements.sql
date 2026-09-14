{{ config(
    materialized='view'
) }}

with source as (

    select
        assignment_id,
        emp_id,
        project_code,
        project_name,
        assignment_role,
        start_date,
        weekly_hours,
        billable,
        source_generated_at
    from {{ source('raw', 'project_assignments_report') }}

)

select
    assignment_id,
    emp_id as employee_id,
    project_code,
    project_name,
    assignment_role,
    start_date as assignment_start_date,
    weekly_hours as assignment_weekly_hours,
    case
        when lower(trim(billable)) in ('y', 'yes') then true
        when lower(trim(billable)) in ('n', 'no') then false
        else null
    end as is_assignment_billable,
    source_generated_at as reference_date
from source
