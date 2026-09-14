{% macro generate_schema_name(custom_schema_name, node) -%}

    {%- set default_schema = target.schema -%}
    
    {%- if custom_schema_name is none -%}
        {% set schema_name = default_schema %}
    {%- else -%}
        {% set schema_name = custom_schema_name | trim %}
    {%- endif -%}

    {%- set git_branch = env_var('GIT_BRANCH', 'main') | replace('origin/', '') | replace('/', '_') -%}
    
    {%- if git_branch != 'main' -%}
        {{ schema_name }}_{{ git_branch }}
    {%- else -%}
        {{ schema_name }}
    {%- endif -%}

{%- endmacro %}