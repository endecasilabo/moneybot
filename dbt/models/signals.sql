create table if not exists {{ this }} (
    id bigserial primary key,
    run_id bigint not null references {{ ref('runs') }} (id),
    ts timestamptz not null default now(),
    symbol text not null,
    session_date date not null,
    last_price numeric not null,
    sma_trend numeric,
    sma_trend_prev numeric,
    sma_exit numeric,
    trend_ok boolean not null,
    pullback_ok boolean not null,
    in_position boolean not null,
    action text not null,
    reason text not null
)
