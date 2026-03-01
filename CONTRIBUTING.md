# Contributing to cqltrack

Thanks for your interest in contributing. This guide covers how to get set up and submit changes.

## Development Setup

```bash
# clone the repo
git clone https://github.com/ereshzealous/cql-track.git
cd cql-track

# create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# install in editable mode with dev dependencies
pip install -e ".[dev]"

# start local Cassandra
docker compose up -d
```

Wait ~60 seconds for Cassandra to become healthy (`docker compose ps`).

## Running Tests

```bash
# all tests
pytest tests/ -v

# specific test file
pytest tests/test_parser.py -v

# specific test
pytest tests/test_parser.py::TestSplitStatements::test_semicolon_in_string -v
```

Tests are pure unit tests — they don't require a running Cassandra instance.

## Manual Testing

```bash
cqltrack init
cqltrack migrate
cqltrack status
cqltrack lint
```

See [USAGE.md](USAGE.md) for the full command reference.

## Submitting Changes

1. Fork the repo and create a branch from `develop`:
   ```bash
   git checkout -b feature/your-feature develop
   ```

2. Make your changes. Follow the existing code style — no linter config to worry about, just keep it consistent with what's there.

3. Add tests for new functionality. Tests go in the `tests/` directory.

4. Make sure all tests pass:
   ```bash
   pytest tests/ -v
   ```

5. Run the linter against example migrations:
   ```bash
   cqltrack lint
   ```

6. Commit with a clear message:
   ```bash
   git commit -m "Add support for X"
   ```

7. Push and open a PR against `develop`.

## Project Structure

```
cqltrack/
  cli.py        Click-based CLI entry point
  config.py     YAML config loading, profiles, env var overrides
  session.py    Cassandra connection factory (plain, SSL, Astra)
  migrator.py   Core migration engine (apply, rollback, validate)
  parser.py     Migration file parsing (filenames, CQL splitting, checksums)
  lock.py       Distributed locking via Cassandra LWT
  linter.py     Static CQL analysis rules
  differ.py     Schema comparison engine
  exceptions.py Custom exception hierarchy
tests/
  test_parser.py   Parser and scanner tests
  test_linter.py   Lint rule tests
  test_differ.py   Schema diff tests
```

## Adding a New Lint Rule

1. Add a `_check_your_rule()` function in `cqltrack/linter.py`
2. Call it from `lint_directory()`
3. Add tests in `tests/test_linter.py`
4. Document the rule in `USAGE.md` under the Lint Rules table

## Adding a New CLI Command

1. Add the command function in `cqltrack/cli.py` decorated with `@main.command()`
2. Add usage docs in `USAGE.md`
3. Update `README.md` command table if it's a user-facing command

## Reporting Issues

Open an issue on GitHub with:
- What you expected to happen
- What actually happened
- cqltrack version (`cqltrack --version`)
- Python version (`python3 --version`)
- Cassandra version

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
