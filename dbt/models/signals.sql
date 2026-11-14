create table if not exists {{ this }} (
    signal_id string not null,
    run_id string not null,
    ts timestamp not null,
    symbol string not null,
    session_date date not null,
    last_price numeric not null,
    sma_trend float64,
    sma_trend_prev float64,
    sma_exit float64,
    trend_ok bool not null,
    pullback_ok bool not null,
    in_position bool not null,
    action string not null,
    reason string not null,
    params json
)
partition by session_date
cluster by symbol
