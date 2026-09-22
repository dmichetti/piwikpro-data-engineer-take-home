{{ config(
    materialized='table'
) }}

with employees as (

    select
        employee_id,
        employee_full_name,
        employee_is_active
    from {{ ref('stg_employees') }}

),

assignments as (

    select
        employee_id,
        project_code,
        project_name,
        assignment_role,
        assignment_weekly_hours,
        is_assignment_billable
    from {{ ref('stg_employee_assignements') }}

),

{#- This must stay a LEFT JOIN starting from assignments, not an INNER JOIN:
    downstream, project_staffing derives its full project list (including
    projects with zero active employees) from this model, so every
    assignment row has to survive regardless of the employee join's outcome.
    Referential integrity is already covered by a relationships test on
    stg_employee_assignements.employee_id, so this is a safety guarantee for
    the future, not a gap in the current data. #}
joined as (

    select
        a.project_code,
        a.project_name,
        a.assignment_role,
        a.assignment_weekly_hours,
        a.is_assignment_billable,
        e.employee_id,
        e.employee_full_name,
        e.employee_is_active
    from assignments a
    left join employees e on a.employee_id = e.employee_id

)

select * from joined
