{{ config(
    materialized='view'
) }}

with source as (

    select
        employee_id,
        first_name as employee_first_name,
        last_name as employee_last_name,
        first_name || ' ' || last_name as employee_full_name,
        email_address as employee_email_address,
        department as employee_department,
        job_title as employee_job_title,
        date_of_hire as employee_hire_date,
        termination_date as employee_termination_date,
        status as employee_status,
        reports_to as employee_reports_to,
        status = 'Active' and termination_date is null as employee_is_active,
        source_generated_at as reference_date
    from {{ source('raw', 'hr_employees_export') }}

)

select * from source
