create table if not exists {{ this }} (
    id bigserial primary key,
    run_id bigint not null references {{ ref('runs') }} (id),
    ts timestamptz not null default now(),
    symbol text not null,
    qty numeric not null,
    avg_entry_price numeric,
    market_value numeric,
    unrealized_pl numeric,
    current_price numeric
)
