{{ config(materialized='view') }}

select *
from {{ ref('runs') }}
qualify row_number() over (partition by run_id order by event_ts desc) = 1
