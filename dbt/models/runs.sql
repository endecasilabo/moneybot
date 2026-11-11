-- Append-only: one row when a run starts (running) and one when it ends. Current state: runs_latest.
create table if not exists {{ this }} (
    run_id string not null,
    job string not null,
    event_ts timestamp not null,
    status string not null,
    detail string
)
partition by date(event_ts)
cluster by job
