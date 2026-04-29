# Contributing

Thanks for contributing to Maestro Flow.

## Scope

Maestro Flow is a local, open-source CLI for reviewable multi-agent software delivery workflows.

When contributing, prefer changes that improve:

- default CLI usability
- run artifact clarity
- provider stability
- host integration quality
- test coverage for core workflow behavior

Avoid mixing unrelated refactors into feature or bug-fix pull requests.

## Local setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -e ".[test]"
```

## Common commands

Run tests:

```bash
python -m pytest -q
```

Run a mock workflow:

```bash
python -m maestro_flow.cli run --mock --requirement "Validate local workflow"
```

Inspect supported providers:

```bash
python -m maestro_flow.cli providers
```

## Contribution guidelines

1. Keep the default user path simple.
2. Prefer improving the CLI-first workflow over host-specific complexity.
3. Add or update tests when changing core behavior.
4. Keep documentation aligned with actual product boundaries.
5. Treat advanced execution features as higher-risk areas and document behavior changes clearly.
6. Use UTF-8 for docs, templates, and user-visible text assets.
7. Avoid introducing mixed encodings or platform-specific line endings in tracked files.

## Pull requests

Please include:

- the problem being solved
- the approach taken
- validation performed
- any behavior changes or compatibility notes

If your change affects a host integration such as Codex, Cursor, Claude, or OpenCode, note that explicitly in the PR description.

## Documentation updates

Update documentation when your change affects:

- the recommended user path
- support matrix or host support status
- provider behavior
- run artifacts
- Codex or VSCode integration assets

## Encoding and text assets

This repository standardizes on:

- UTF-8 text encoding
- LF line endings for tracked text files

If you edit docs, templates, or integration assets, please keep them in UTF-8 and verify user-visible text remains readable in the target host environment.

## Release-minded changes

For changes that affect public behavior, prefer adding an entry under `## [Unreleased]` in [CHANGELOG.md](/D:/Project/test-project/multi-agent/CHANGELOG.md).
