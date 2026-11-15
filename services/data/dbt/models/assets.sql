create table if not exists {{ this }} (
    symbol string not null,
    name string,
    asset_class string,
    exchange string,
    active bool,
    updated_at timestamp not null
)
cluster by symbol
