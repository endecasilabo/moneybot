{{ config(materialized='view') }}

select *
from {{ ref('order_intents') }}
qualify row_number() over (partition by client_order_id order by event_ts desc) = 1
