create table if not exists {{ this }} (
    id bigserial primary key,
    job text not null,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    status text not null,
    detail text
)
