# HP 6033A maintainer guide

## Current sources

This repository owns the standalone HP 6033A application, dashboards, operating manual, screenshots and original installer/updater. [Instrument Suite](https://github.com/RLF62/instrument-suite) owns signed multi-controller installation, shared-adapter integration and coordinated recovery.

Use the [documentation index](DOCUMENTATION.md) to choose the correct operating or installation guide. Earlier task lists and deployment snapshots are retained in Git history.

## Before changing code

Read the relevant implementation, templates, tests and deployment guides. Compare deployed host-specific wrappers and settings before replacing application files. Keep live configuration, authentication, certificates and private backups outside source control.

A standalone direct-VISA controller and a suite-patched shared-broker controller have different hardware ownership contracts. Do not copy one over the other. Preserve instrument output and settings, run applicable checks on a development host, and record the exact source revision and backup before activation.

## Releases

Signed suite updates use immutable versioned packages selected by the suite manifest. Never replace an already-published artifact to correct code; build a new version. Documentation-only repository cleanup does not alter published release bytes or installed applications.

See [current release acceptance](https://github.com/RLF62/instrument-suite/blob/main/FRESH_CARD_VALIDATION.md) for completed checks and limits. Physical Android touch checks and hardware-specific behaviors require their own evidence.
