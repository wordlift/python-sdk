# Packaging Slices for v7

`wordlift-sdk` v7 keeps the `wordlift_sdk` import namespace but changes the
distribution model:

- Base install: `pip install wordlift-sdk`
- Explicit core alias: `pip install "wordlift-sdk[core]"`
- Full install: `pip install "wordlift-sdk[all]"`
- Feature install: `pip install "wordlift-sdk[validation]"`, etc.

## Design Goals

- Reduce default install weight.
- Preserve the existing import namespace.
- Keep feature discovery simple for clients.
- Fail with an install hint when a feature export is accessed without its extra.

## Slice Map

- `core`
  - Default install target.
  - Includes lightweight client/configuration primitives and lazy package entry
    points.
  - Does not install Playwright, SHACL, pandas, rdflib, Google auth, or
    YARRRML dependencies.

- `render`
  - Modules: `wordlift_sdk.render.*`
  - Dependencies: `playwright`, `lxml`

- `validation`
  - Modules: `wordlift_sdk.validation.*`
  - Dependencies: `pyshacl`, `rdflib`, `requests`, `tqdm`

- `google-sheets`
  - Modules: `wordlift_sdk.google_sheets.*`
  - Dependencies: `google-auth`, `gspread`, `pandas`

- `google-search-console`
  - Modules: `wordlift_sdk.google_search_console.*`
  - Dependencies: `google-auth`, `pandas`, `pycountry`, `tqdm`, `twisted`

- `ingestion`
  - Modules: `wordlift_sdk.ingestion.*`, most `wordlift_sdk.url_source.*`
  - Dependencies: `advertools`, `google-auth`, `gspread`, `lxml`,
    `morph-kgc`, `worph`, `pandas`, `playwright`, `pyshacl`, `rdflib`, `requests`,
    `tqdm`, `trafilatura`
  - Notes: intentionally broad because the public ingestion package also exports
    inventory and classification helpers; this is a DX-first slice, not the
    finest-grained possible split.

- `structured-data`
  - Modules: `wordlift_sdk.structured_data.*`
  - Dependencies: `advertools`, `lxml`, `morph-kgc`, `worph`, `playwright`, `pyshacl`,
    `rdflib`, `requests`, `tqdm`

- `workflow`
  - Modules: `wordlift_sdk.workflow.*`, `wordlift_sdk.container.*`,
    `wordlift_sdk.protocol.*`, root `run_kg_import_workflow`
  - Dependencies: `advertools`, `gql`, `google-auth`, `gspread`, `lxml`,
    `pandas`, `playwright`, `pydantic-core`, `rdflib`, `tqdm`
  - Notes: this preserves the legacy import workflow path while keeping it out
    of the base install.

- `graph`
  - Modules: `wordlift_sdk.graph.*`
  - Dependencies: `pyshacl`, `python-liquid`, `rdflib`, `requests`, `tomli`,
    `tqdm`

- `kg-build`
  - Modules: `wordlift_sdk.kg_build.*`
  - Dependencies: `advertools`, `gql`, `google-auth`, `gspread`, `jinja2`,
    `lxml`, `morph-kgc`, `worph`, `pandas`, `playwright`, `pydantic-core`, `pyshacl`,
    `PyICU`, `python-liquid`, `rdflib`, `requests`, `tomli`, `tqdm`, `trafilatura`
  - Notes: this is intentionally broad because `kg_build` composes multiple
    subsystems.

- `legacy`
  - Compatibility-oriented umbrella for older surfaces such as `entity`,
    `internal_link`, `kg`, deprecated helpers, and related utilities.

- `all`
  - Installs every optional dependency declared above.

## Native ICU for kg-build

Only `kg-build` and `all` install `PyICU==2.16.2`. PyICU builds from source and
requires ICU development headers/libraries, `pkg-config`, and a C++ compiler.
The canonical transliteration baseline is ICU **74.2**. Pin the native ICU
version as well as PyICU in deployment images: ICU data changes can otherwise
change generated IDs. Non-ASCII canonicalization rejects a different linked
ICU version with an actionable error; ASCII-only normalization is unchanged.
CI uses Ubuntu 24.04 and checks this version explicitly.

On Ubuntu 24.04:

```bash
sudo apt-get update
sudo apt-get install -y libicu-dev pkg-config g++
test "$(pkg-config --modversion icu-i18n)" = "74.2"
uv pip install "wordlift-sdk[kg-build]"
```

On other platforms, provision ICU 74.2 and set `PKG_CONFIG_PATH` to its
`lib/pkgconfig` directory before installing the extra. A newer system ICU is
not an equivalent replacement for reproducible canonical IDs. For example,
with an existing ICU 74.2 installation under `/opt/local` on macOS:

```bash
export PKG_CONFIG_PATH="/opt/local/lib/pkgconfig"
test "$(pkg-config --modversion icu-i18n)" = "74.2"
uv pip install "wordlift-sdk[kg-build]"
```

If PyICU was already compiled against another ICU, rebuild it after selecting
the 74.2 `PKG_CONFIG_PATH` (`uv pip install --reinstall --no-cache pyicu==2.16.2`).

Postprocessor interpreters configured separately must install the same extra
and native ICU version. Check the linked runtime after installation:

```bash
python -c 'import icu; print(icu.VERSION, icu.ICU_VERSION)'
# 2.16.2 74.2
```

## Boundary Rules

- Package `__init__` modules must stay lazy so importing `wordlift_sdk` or a
  feature package does not immediately import heavy transitive dependencies.
- Cross-feature imports are acceptable inside implementation modules, but public
  package exports should remain lazy and point users to the matching extra when
  dependencies are missing.
- New features should land in an existing slice unless they introduce a clearly
  separate dependency cluster.

## Testing Strategy

- The slice contract is encoded in `tests/tools/run_slice_tests.py`.
- Fast import smoke coverage is encoded in `tests/tools/run_slice_smoke_imports.py`.
- Negative install-hint checks for lean installs are encoded in
  `tests/tools/check_missing_extra_hints.py`.
- Each slice maps to a representative pytest subset for its public API and
  dependency cluster.
- CI should install the matching extra and run:

```bash
poetry run python tests/tools/run_slice_smoke_imports.py validation
poetry run python tests/tools/run_slice_tests.py validation
poetry run python tests/tools/run_slice_tests.py structured-data
```

- `all` remains the full regression suite and coverage gate.
- `core` should also run the negative hint check to verify that accessing
  excluded feature exports fails with a targeted `wordlift-sdk[...]` message.
- When a new public feature lands in a slice, update both the extra definition
  and the slice test target list in the same change.

## Follow-Up Opportunities

- Split `ingestion` into finer extras later if install size still matters:
  `ingestion-sources`, `ingestion-playwright`, `ingestion-classification`.
- Move legacy-only helpers behind narrower extras once client usage is known.
- Add CI jobs that install and smoke-test `core`, `validation`, `structured-data`,
  and `all` independently.
