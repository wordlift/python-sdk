# Shared SDK Customer Project Contract

Use this contract when running a shared SDK-based profile workflow across multiple customer repositories.

## Goal

Keep `wordlift_sdk.kg_build` as a reusable engine while each customer repo provides only profile config, mappings, templates, and postprocessors.

## Runtime Model

- The workflow runs in one Python environment.
- The customer repository is the runtime project context.
- Paths are resolved from the current working directory (`cwd`) unless absolute paths are provided.

Run from project root with your host workflow command.

## Required Project Layout

Each customer repo must provide:

```text
worai.toml
profiles/
  _base/
    postprocessors.toml   # optional
  <profile_name>/
    mappings/
    templates/
    postprocessors.toml   # optional
```

Minimum profile requirements:

- `api_key` (direct or env interpolation)
- `sheets_service_account` (JSON string or file path)
- Source definition:
- `urls` list, or
- `sheets_url` + `sheets_name`

## Postprocessor Loading Contract

Execution order:

1. Built-in core ID postprocessor
2. entries from `profiles/_base/postprocessors.toml`
3. entries from `profiles/<profile>/postprocessors.toml`

Manifest contract:

- top-level defaults are optional:
  - `python = "./.venv/bin/python"`
  - `timeout_seconds = 120`
  - `enabled = true`
  - `keep_temp_on_error = false`
- each entry is a `[[postprocessors]]` table:
  - required: `class = "package.module:ClassName"`
  - optional overrides: `python`, `timeout_seconds`, `enabled`, `keep_temp_on_error`
- list order is execution order.
- on failure, workflow fails fast.

Execution contract:

- `wordlift_sdk.kg_build` runs each class in a subprocess.
- working directory is repo root.
- subprocesses inherit the parent environment as-is; SDK does not inject or rewrite
  `PYTHONPATH`.
- graph exchange uses temp files in N-Quads:
  - input: `input_graph.nq`
  - output: `output_graph.nq`
- context exchange uses temp JSON file (`context.json`) with:
  - `profile_name`, `url`
  - `dataset_uri`, `country_code`
  - `exports`, `settings`
  - `response.id`, `response.web_page.url`, `response.web_page.html`

## Dependency Contract

Postprocessor classes are imported in the interpreter configured by manifest `python` (or its default). That interpreter must include every imported package.

Recommended patterns:

1. Use repo-local `.venv/bin/python` in manifest defaults for customer-specific dependencies.
2. Publish shared processors in a reusable package and install it in the workflow interpreter.
3. Avoid customer-specific imports from unrelated repos.

## Compatibility Checklist

Use this checklist before onboarding a customer repo.

- [ ] Running command from repo root works with the host project workflow entrypoint.
- [ ] `worai.toml` contains expected profiles and resolves all `${ENV_VAR}` placeholders
- [ ] Profile has a valid input source (`urls` or `sheets_url` + `sheets_name`)
- [ ] `sheets_service_account` is valid JSON or a valid readable path
- [ ] `profiles/<name>/mappings` exists and contains the default/target mapping
- [ ] `profiles/<name>/templates` exists (or profile intentionally has none)
- [ ] `profiles/_base/postprocessors.toml` exists (or intentionally absent)
- [ ] `profiles/<name>/postprocessors.toml` exists (or intentionally absent)
- [ ] Every postprocessor class import resolves in the configured interpreter (`python` field/default)
- [ ] `--debug` run writes output under `output/debug_cloud/<profile>/`
- [ ] At least one smoke test profile run completes without callback/postprocessor exceptions

## Suggested Onboarding Workflow

1. Copy this contract file into the customer repo (or keep a centrally versioned copy).
2. Create/verify profile directories and `worai.toml`.
3. Configure profile/base `postprocessors.toml` with class entries and interpreter defaults.
4. Run one profile in debug mode.
5. Validate debug output and patching behavior.
6. Add project-specific CI smoke command for one representative profile.

## Standard Smoke Command (Runner Contract)

```bash
python -m wordlift_sdk.kg_build.postprocessor_runner \
  --class my_project.postprocessors.sample:SamplePostprocessor \
  --input-graph /abs/path/to/input_graph.nq \
  --output-graph /abs/path/to/output_graph.nq \
  --context /abs/path/to/context.json
```
