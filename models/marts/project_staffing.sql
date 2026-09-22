{{ config(
    materialized='table'
) }}

with assignments as (
    select *
    from {{ ref('int_employee_assignements') }}
),

{#- Every project that has at least one assignment record, active or not:
    this is what lets a project with zero active employees still appear
    below. int_employee_assignements preserves every assignment row
    regardless of employee status  #}
projects as (
    select distinct project_code, project_name
    from assignments
),

active_assignments as (
    select *
    from assignments
    where employee_is_active
),

{#- When a project has more than one active Lead, pick the one with the
    most weekly_hours as the primary lead (employee_id as a tiebreaker for
    full determinism). The anomaly itself is flagged independently upstream,
    see tests/warn_multiple_active_leads_per_project.sql - not surfaced as a
    column here. #}
leads_ranked as (
    select
        project_code,
        employee_full_name,
        row_number() over (
            partition by project_code
            order by assignment_weekly_hours desc, employee_id
        ) as lead_rank
    from active_assignments
    where assignment_role = 'Lead'
),

leads as (
    select
        project_code,
        employee_full_name as project_lead
    from leads_ranked
    where lead_rank = 1
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
),

final as (
    select
        p.project_code,
        p.project_name,
        l.project_lead,
        coalesce(t.project_team_size, 0) as project_team_size,
        coalesce(t.project_billable_team_size, 0) as project_billable_team_size,
        cast(coalesce(t.project_total_weekly_hours, 0) as bigint) as project_total_weekly_hours,
        cast(coalesce(t.project_total_billable_weekly_hours, 0) as bigint) as project_total_billable_weekly_hours
    from projects p
    left join leads l on p.project_code = l.project_code
    left join team t on p.project_code = t.project_code
)

select
    *,
    current_date as refreshed_date
from final
