create table if not exists {{ this }} (
    id bigserial primary key,
    run_id bigint not null references {{ ref('runs') }} (id),
    ts timestamptz not null default now(),
    equity numeric,
    cash numeric,
    buying_power numeric,
    portfolio_value numeric,
    open_orders jsonb not null
)
