CREATE TABLE IF NOT EXISTS runs (
    id bigserial PRIMARY KEY,
    job text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status text NOT NULL,
    detail text
);

CREATE TABLE IF NOT EXISTS signals (
    id bigserial PRIMARY KEY,
    run_id bigint NOT NULL REFERENCES runs (id),
    ts timestamptz NOT NULL DEFAULT now(),
    symbol text NOT NULL,
    session_date date NOT NULL,
    last_price numeric NOT NULL,
    sma_trend numeric,
    sma_trend_prev numeric,
    sma_exit numeric,
    trend_ok boolean NOT NULL,
    pullback_ok boolean NOT NULL,
    in_position boolean NOT NULL,
    action text NOT NULL,
    reason text NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    client_order_id text PRIMARY KEY,
    run_id bigint NOT NULL REFERENCES runs (id),
    alpaca_order_id text,
    symbol text NOT NULL,
    side text NOT NULL,
    qty numeric NOT NULL,
    time_in_force text NOT NULL,
    status text,
    submitted_at timestamptz NOT NULL DEFAULT now(),
    filled_avg_price numeric,
    error text
);

CREATE TABLE IF NOT EXISTS account_snapshots (
    id bigserial PRIMARY KEY,
    run_id bigint NOT NULL REFERENCES runs (id),
    ts timestamptz NOT NULL DEFAULT now(),
    equity numeric,
    cash numeric,
    buying_power numeric,
    portfolio_value numeric,
    open_orders jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS position_snapshots (
    id bigserial PRIMARY KEY,
    run_id bigint NOT NULL REFERENCES runs (id),
    ts timestamptz NOT NULL DEFAULT now(),
    symbol text NOT NULL,
    qty numeric NOT NULL,
    avg_entry_price numeric,
    market_value numeric,
    unrealized_pl numeric,
    current_price numeric
);
