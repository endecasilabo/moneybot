-- Append-only: trigger writes pending, execute appends sent/skipped/error/expired. Current state: order_intents_latest.
create table if not exists {{ this }} (
    client_order_id string not null,
    event_ts timestamp not null,
    session_date date not null,
    symbol string not null,
    side string not null,
    qty numeric not null,
    status string not null,
    signal_id string,
    run_id string not null,
    detail string
)
partition by session_date
cluster by symbol
