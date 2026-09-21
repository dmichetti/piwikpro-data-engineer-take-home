{% macro generate_schema_name(custom_schema_name, node) -%}

    {%- set default_schema = target.schema -%}
    
    {%- if custom_schema_name is none -%}
        {% set schema_name = default_schema %}
    {%- else -%}
        {% set schema_name = custom_schema_name | trim %}
    {%- endif -%}

    {#- GIT_BRANCH must already be a safe suffix (lowercase, [a-z0-9_]); the caller sanitizes it. #}
    {%- set git_branch = env_var('GIT_BRANCH', 'main') -%}
    
    {%- if git_branch not in ['main', 'master'] -%}
        {{ schema_name }}_{{ git_branch }}
    {%- else -%}
        {{ schema_name }}
    {%- endif -%}

{%- endmacro %}