-- Migration: add status to users

  ALTER TABLE users ADD status text;

  -- @down
  ALTER TABLE users DROP status;