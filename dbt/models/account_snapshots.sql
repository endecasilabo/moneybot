create table if not exists {{ this }} (
    run_id string not null,
    ts timestamp not null,
    equity numeric,
    cash numeric,
    buying_power numeric,
    portfolio_value numeric,
    open_orders json not null
)
partition by date(ts)
