# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-01

### Added

- Core migration engine: `init`, `migrate`, `rollback` commands
- Version-controlled `.cql` migration files with `V<version>__<description>.cql` naming
- `-- @down` sections for rollback support
- Distributed locking via Cassandra Lightweight Transactions (LWT) with configurable TTL
- MD5 checksum validation to detect modified migration files
- `validate` and `repair` commands for checksum management
- `baseline` command for adopting cqltrack on existing databases
- `status` command showing applied and pending migrations
- `history` command with full audit trail (who, when, duration, status)
- `pending` command as CI gate (exit code 1 if unapplied migrations exist)
- `new` command to scaffold migration files
- Partial failure handling: failed migrations tracked and retryable
- Schema agreement waiting between DDL statements
- Multi-environment profiles in YAML config (`--profile dev/staging/prod`)
- Configuration via YAML file, environment variables, and CLI flags
- Static CQL linter with 8 rules for dangerous patterns
- Schema snapshot export (`snapshot` command)
- Schema diff between keyspaces or environments (`diff` command)
- SSL/TLS support including mutual TLS
- DataStax Astra DB support via secure connect bundle
- Configurable consistency levels and connection timeouts
- JSON output mode for all read commands (`--json`)
- Docker support with multi-stage Dockerfile
- Docker Compose for local Cassandra development
- GitHub Actions CI pipeline (Python 3.9, 3.11, 3.13)
- 48 unit tests covering parser, linter, and differ

[0.1.0]: https://github.com/ereshzealous/cql-track/releases/tag/v0.1.0
