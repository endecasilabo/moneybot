{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        tags=['staging'],
        unique_key=['id'],
        on_schema_change='sync_all_columns',
        partition_by={
            'field': 'created_at',
            'data_type': 'timestamp',
            'granularity': 'day',
        },
        
    )
}}

create table if not exists {{ this }} (
    symbol text not null,
    feed text not null,
    timeframe text not null,
    ts timestamptz not null,
    open numeric not null,
    high numeric not null,
    low numeric not null,
    close numeric not null,
    volume numeric not null,
    trade_count bigint,
    vwap numeric,
    run_id bigint not null references {{ ref('runs') }} (id),
    primary key (symbol, feed, timeframe, ts)
)
