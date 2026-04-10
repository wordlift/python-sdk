# Versioning Specs

## Scheme

The project follows [Semantic Versioning 2.0.0](https://semver.org/).

## Tag Format

Canonical release tags use the `v<x.y.z>` format (for example `v8.0.10`).
Bare semver tags (`x.y.z`) are tolerated by publish automation for backward
compatibility, but new manual release tags should use the `v` prefix.

## Management

Versions are managed using `poetry`.

To bump a version:
```bash
poetry version <major|minor|patch>
```

## Release Process

1.  **Bump Version:** Use `poetry version` to increment the version in `pyproject.toml`.
2.  **Update Dependencies:** If the `wordlift-client` or other core dependencies need updates, apply them.
3.  **Update release docs/specs:** For major packaging or API changes, update the
    relevant docs/specs and changelog entries in the same change.
4.  **Major-release note:** A major version is required when install/runtime
    contracts change in a way that affects existing clients, including package
    slicing and optional-dependency boundaries.
5.  **Commit:**
    *   Stage `pyproject.toml` and `poetry.lock`.
    *   Commit message format: `chore: Bump version to <version>`.
6.  **Tag:**
    *   Create an annotated git tag using the `v`-prefixed version:
        `git tag -a v<version> -m "v<version>"`.
7.  **Push:**
    *   Push the commit and the tag to the remote repository.
