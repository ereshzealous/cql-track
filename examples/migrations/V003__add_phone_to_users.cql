-- Migration: add phone column to users

ALTER TABLE users ADD phone text;

-- @down
ALTER TABLE users DROP phone;
