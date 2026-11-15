{{ config(materialized='view') }}

select *
from {{ source('collector', 'runs') }}
qualify row_number() over (partition by run_id order by event_ts desc) = 1
