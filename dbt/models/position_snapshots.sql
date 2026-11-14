create table if not exists {{ this }} (
    run_id string not null,
    ts timestamp not null,
    symbol string not null,
    qty numeric not null,
    avg_entry_price numeric,
    market_value numeric,
    unrealized_pl numeric,
    current_price numeric
)
partition by date(ts)
cluster by symbol
