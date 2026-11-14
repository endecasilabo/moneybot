-- Append-only: one row per order event (sent, duplicate, error, later fills). Current state: orders_latest.
create table if not exists {{ this }} (
    client_order_id string not null,
    run_id string not null,
    event_ts timestamp not null,
    alpaca_order_id string,
    symbol string not null,
    side string not null,
    qty numeric not null,
    time_in_force string not null,
    status string,
    filled_avg_price numeric,
    error string
)
partition by date(event_ts)
cluster by symbol
