select
    symbol,
    feed,
    timeframe,
    ts,
    open,
    high,
    low,
    close,
    volume,
    trade_count,
    vwap
from {{ source('collector', 'base_bar') }}
