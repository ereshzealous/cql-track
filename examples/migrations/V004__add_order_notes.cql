-- Migration: add notes column to orders

ALTER TABLE orders ADD notes text;

-- @down
ALTER TABLE orders DROP notes;
