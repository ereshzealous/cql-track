-- Migration: add audit log

  CREATE TABLE IF NOT EXISTS audit_log (
      id   UUID,
      msg  text,
      ts   timestamp,
      PRIMARY KEY (id)
  );

  -- @down
  DROP TABLE IF EXISTS audit_log;