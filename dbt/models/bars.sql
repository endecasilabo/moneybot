-- Written by the ingest job with MERGE on (symbol, timeframe, ts). ts is the bar start, UTC.
create table if not exists {{ this }} (
    symbol string not null,
    timeframe string not null,
    ts timestamp not null,
    open float64 not null,
    high float64 not null,
    low float64 not null,
    close float64 not null,
    volume float64,
    trade_count int64,
    vwap float64,
    feed string not null,
    adjustment string not null,
    ingested_at timestamp not null,
    run_id string
)
partition by date(ts)
cluster by symbol, timeframe
