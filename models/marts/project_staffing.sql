{{ config(
    materialized='table'
) }}

with employees as (

    select
        employee_id,
        employee_full_name
    from {{ ref('stg_employees') }}
    where employee_is_active

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

{#- Every project that has at least one assignment record, active or not:
    this is what lets a project with zero active employees still appear
    below. Sourced from assignments directly, not the employee join, so it's
    unaffected by the active-employee filter above. -#}
projects as (
    select distinct project_code, project_name
    from assignments
),

active_assignments as (
    select
        a.project_code,
        a.assignment_role,
        a.assignment_weekly_hours,
        a.is_assignment_billable,
        e.employee_id,
        e.employee_full_name
    from assignments a
    inner join employees e on a.employee_id = e.employee_id
),

leads as (
    select
        project_code,
        string_agg(employee_full_name, ', ' order by employee_id) as project_lead,
        count(*) as project_lead_count
    from active_assignments
    where assignment_role = 'Lead'
    group by project_code
),

team as (
    select
        project_code,
        count(distinct employee_id) as project_team_size,
        count(distinct employee_id) filter (where is_assignment_billable) as project_billable_team_size,
        sum(assignment_weekly_hours) as project_total_weekly_hours,
        sum(
            case when is_assignment_billable then assignment_weekly_hours else 0 end
        ) as project_total_billable_weekly_hours
    from active_assignments
    group by project_code
)

select
    p.project_code,
    p.project_name,
    l.project_lead,
    coalesce(l.project_lead_count, 0) as project_lead_count,
    coalesce(t.project_team_size, 0) as project_team_size,
    coalesce(t.project_billable_team_size, 0) as project_billable_team_size,
    {#- sum() over a bigint column widens to duckdb's hugeint by default;
        cast back down since these totals never approach that range. -#}
    cast(coalesce(t.project_total_weekly_hours, 0) as bigint) as project_total_weekly_hours,
    cast(coalesce(t.project_total_billable_weekly_hours, 0) as bigint) as project_total_billable_weekly_hours
from projects p
left join leads l on p.project_code = l.project_code
left join team t on p.project_code = t.project_code
