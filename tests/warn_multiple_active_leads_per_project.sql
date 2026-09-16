{#- Flags any project with more than one active Lead. This is a known,
    legitimate case in the current data (one project) - warn_if surfaces it
    without failing the build; error_if escalates only if it ever spreads to
    more than 2 projects, since that would suggest a systemic problem rather
    than an isolated, already-understood anomaly.

    Each row returned here is one affected project, so warn_if/error_if
    threshold on the number of *projects* with the issue, not on individual
    assignment rows. #}
{{ config(warn_if='>0', error_if='>2') }}

select
    project_code,
    count(*) as active_lead_count
from {{ ref('int_employee_assignements') }}
where assignment_role = 'Lead'
  and employee_is_active
group by project_code
having count(*) > 1
