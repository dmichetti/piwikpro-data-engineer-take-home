{% test not_null_empty_string(model, column_name) %}

with validation as (
    select {{ column_name }} as null_empty_field
    from {{ model }}
),

validation_errors as (
    select 1
    from validation
    where coalesce(null_empty_field,'') =''
)

select *
from validation_errors

{% endtest %}