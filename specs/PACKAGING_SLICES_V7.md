# Packaging Slices V7

## Goal

`wordlift-sdk` v7 keeps the `wordlift_sdk` import namespace while moving to a
lean base install plus optional extras.

## Contract

- Base install: `pip install wordlift-sdk`
- Explicit core alias: `pip install "wordlift-sdk[core]"`
- Feature installs: `pip install "wordlift-sdk[validation]"`, etc.
- Full install: `pip install "wordlift-sdk[all]"`
- The README must publish the full slice list, one-line purpose per slice, and
  at least one example verification command sequence for slice tooling.

## Slice Names

The declared slice/extra names are:

- `core`
- `google-sheets`
- `render`
- `validation`
- `google-search-console`
- `ingestion`
- `structured-data`
- `workflow`
- `graph`
- `kg-build`
- `legacy`
- `all`

## Runtime Behavior

- Public package exports must remain lazy so importing `wordlift_sdk` or a
  feature package does not immediately import heavy transitive dependencies.
- Accessing a feature export without the matching extra installed must raise a
  `ModuleNotFoundError` with a targeted install hint in the form
  `wordlift-sdk[<extra>]`.

## Verification Contract

Slice verification is part of the repository contract:

- `tests/tools/run_slice_smoke_imports.py` validates per-slice public imports
  and key callable smoke paths.
- `tests/tools/run_slice_tests.py` defines the representative pytest scope for
  each slice.
- `tests/tools/check_missing_extra_hints.py` validates that lean installs fail
  with targeted install hints when excluded feature exports are accessed.

CI must run:

1. install only the slice extra
2. run slice smoke imports
3. for `core`, run missing-extra hint checks
4. run the slice pytest scope
5. separately, run `all` with the full regression suite and coverage gate

## Documentation Contract

- `README.md` is the consumer-facing summary for packaging slices.
- `docs/packaging_slices_v7.md` is the detailed human-readable reference.
- `specs/PACKAGING_SLICES_V7.md` is the normative packaging contract.
- Changes to extras, slice names, lazy-export behavior, or slice verification
  tooling must update all three in the same change.
