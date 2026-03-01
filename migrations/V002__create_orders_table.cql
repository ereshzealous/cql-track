-- Migration: create orders table
-- Orders partitioned by user for efficient lookups

CREATE TABLE IF NOT EXISTS orders (
    user_id    UUID,
    order_id   UUID,
    product    text,
    quantity   int,
    total      decimal,
    status     text,
    created_at timestamp,
    PRIMARY KEY (user_id, order_id)
) WITH CLUSTERING ORDER BY (order_id DESC);

-- @down
DROP TABLE IF EXISTS orders;
