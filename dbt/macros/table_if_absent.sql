-- ponytail: creates a missing table and leaves an existing one alone.
-- A later column change is not applied. Upgrade path: a migration that alters the table.

{% materialization table_if_absent, adapter='bigquery' %}
  {%- set existing_relation = load_cached_relation(this) -%}
  {%- set target_relation = this.incorporate(type='table') -%}

  {% if existing_relation is none %}
    {% call statement('main') -%}
      {{ sql }}
    {%- endcall %}
  {% else %}
    {% call statement('main') -%}
      select 1
    {%- endcall %}
  {% endif %}

  {{ return({'relations': [target_relation]}) }}
{% endmaterialization %}
