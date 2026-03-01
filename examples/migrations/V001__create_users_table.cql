-- Migration: create users table

CREATE TABLE IF NOT EXISTS users (
    user_id    UUID,
    email      text,
    name       text,
    created_at timestamp,
    PRIMARY KEY (user_id)
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- @down
DROP INDEX IF EXISTS idx_users_email;
DROP TABLE IF EXISTS users;
