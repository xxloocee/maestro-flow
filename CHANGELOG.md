# Changelog

All notable changes to this project will be documented in this file.

This project loosely follows Keep a Changelog and uses semantic versioning as a release guideline.

## [Unreleased]

### Added

- Added opt-in `--json` output mode for key CLI commands, including `run`, `spec run`, `install`, `ci evaluate`, and `sync-back` operations

### Changed

- Fixed sync-back user-facing messages to use readable UTF-8 Chinese text

## [0.1.0] - 2026-04-29

### Added

- Initial open-source release of Maestro Flow as a local multi-agent delivery CLI
- Requirement-driven and spec-driven workflow entry points
- Structured run artifacts under `.maestro/runs/<run_id>/`
- Policy gate, CI evaluation, and PR comment support
- Host integration templates for:
  - `opencode`
  - `claude`
  - `cursor`
  - `antigravity`
- Codex default-path skills:
  - `maestro-spec`
  - `maestro-run`
- MVP definition, support boundary, validated setup, regression sample, and release checklist documentation
- Release smoke tests and CI package build verification

### Changed

- README restructured for open-source first-run experience
- Runtime dependencies simplified to use `pyproject.toml` as the primary source of truth
- Codex integration wording normalized around skills instead of separate VSCode Codex handling
