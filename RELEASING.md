# Branching & Release Strategy

## Branches

```
main        ← stable releases only, always deployable
develop     ← active development, PRs merge here
release/*   ← release prep (created automatically by workflow)
feature/*   ← feature branches (off develop)
hotfix/*    ← urgent fixes (off main)
```

### main

- Protected. Only receives merges from `release/*` and `hotfix/*` branches.
- Every commit on `main` is a tagged release.
- Default branch on GitHub.

### develop

- Primary working branch. All feature PRs target `develop`.
- Always ahead of or equal to `main`.
- CI runs on every push.

### release/*

- Created automatically by the Release workflow.
- Named `release/v1.2.0` or `release/v1.2.0-beta.1`.
- Contains the version bump commit.
- Merged to `main` (stable) or tagged directly (beta), then merged back to `develop`.

### feature/*

- Branched from `develop`, merged back via PR.
- Naming: `feature/add-dry-run-mode`, `feature/scylladb-support`.
- Deleted after merge.

### hotfix/*

- Branched from `main` for urgent production fixes.
- Merged to both `main` (with tag) and `develop`.
- Naming: `hotfix/fix-lock-timeout`.

## Versioning

Follows [Semantic Versioning](https://semver.org/):

```
MAJOR.MINOR.PATCH[-beta.N]
```

| Bump | When | Example |
|------|------|---------|
| **major** | Breaking changes to CLI, config format, or migration file format | 1.0.0 → 2.0.0 |
| **minor** | New commands, features, config options (backwards compatible) | 1.0.0 → 1.1.0 |
| **patch** | Bug fixes, documentation, internal improvements | 1.0.0 → 1.0.1 |
| **beta** | Pre-release for the next minor version | 1.0.0 → 1.1.0-beta.1 → 1.1.0-beta.2 → 1.1.0 |

### What counts as a breaking change?

- Removing or renaming a CLI command or option
- Changing the migration file naming convention
- Changing the `cqltrack_history` table schema in a non-additive way
- Changing config file format in a non-backwards-compatible way
- Dropping support for a Python version

### What does NOT count as breaking?

- Adding new commands or options
- Adding new config keys with defaults
- Adding columns to tracking tables
- New lint rules

## Release Process

### Automated (recommended)

Releases are triggered from GitHub Actions:

1. Go to **Actions** → **Release** → **Run workflow**
2. Select the version bump type: `patch`, `minor`, `major`, or `beta`
3. Optionally enable **dry run** to preview without pushing

The workflow will:
- Checkout `develop`
- Run all tests
- Calculate the next version
- Create a `release/vX.Y.Z` branch with the version bump
- **Stable release**: merge to `main`, tag, create GitHub Release, merge back to `develop`
- **Beta release**: tag on the release branch, create pre-release on GitHub, merge back to `develop`

### Version flow examples

**Stable release (patch):**
```
develop (1.0.0) → release/v1.0.1 → main (tagged v1.0.1) → merged back to develop (1.0.1)
```

**Beta release:**
```
develop (1.0.0) → release/v1.1.0-beta.1 (tagged v1.1.0-beta.1) → merged back to develop (1.1.0-beta.1)
```

**Second beta:**
```
develop (1.1.0-beta.1) → release/v1.1.0-beta.2 (tagged v1.1.0-beta.2) → merged back to develop (1.1.0-beta.2)
```

**Promote beta to stable:**
```
develop (1.1.0-beta.2) → select "minor" → release/v1.1.0 → main (tagged v1.1.0) → merged back to develop (1.1.0)
```

### Hotfix process (manual)

For urgent fixes that can't wait for the next release:

```bash
# branch from main
git checkout main
git checkout -b hotfix/fix-lock-timeout

# fix, test, commit
git commit -m "Fix lock timeout not respected on retry"

# merge to main and tag
git checkout main
git merge --no-ff hotfix/fix-lock-timeout -m "Hotfix v1.0.1"
git tag -a v1.0.1 -m "Hotfix: fix lock timeout"
git push origin main v1.0.1

# merge back to develop
git checkout develop
git merge --no-ff main -m "Merge hotfix v1.0.1 back to develop"
git push origin develop

# clean up
git branch -d hotfix/fix-lock-timeout
```

## Day-to-Day Workflow

### Adding a feature

```bash
git checkout develop
git pull origin develop
git checkout -b feature/my-feature

# work, commit, push
git push origin feature/my-feature

# open PR targeting develop
# after review and CI passes, merge
```

### Making a release

1. Ensure `develop` has everything you want to release
2. Go to GitHub Actions → Release → Run workflow
3. Pick `minor` (new features), `patch` (fixes), or `beta` (pre-release)
4. Workflow handles the rest

### Testing a beta

```bash
pip install cql-track==1.1.0b1  # when published to PyPI
```

Beta versions are marked as pre-release on GitHub and won't be installed by default with `pip install cql-track`.
