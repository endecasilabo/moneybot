{{ config(materialized='view') }}

select *
from {{ source('collector', 'orders') }}
qualify row_number() over (partition by client_order_id order by event_ts desc) = 1
