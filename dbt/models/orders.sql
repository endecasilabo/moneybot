create table if not exists {{ this }} (
    client_order_id text primary key,
    run_id bigint not null references {{ ref('runs') }} (id),
    alpaca_order_id text,
    symbol text not null,
    side text not null,
    qty numeric not null,
    time_in_force text not null,
    status text,
    submitted_at timestamptz not null default now(),
    filled_avg_price numeric,
    error text
)
