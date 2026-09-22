{% test row_exists(model) -%}
    select COUNT(*)
    from (
        select *
        from {{ model }}
        limit 1
    )
    having COUNT(*)=0
{% endtest -%}