# Production migration comparison gate

The production installation remains running with its existing HTTPS gateway,
authentication, controller services, settings and runtime layout. No updater
enrollment or controller activation was performed during this review. A private
recovery archive includes application files and runtimes, authentication,
certificates, systemd, Nginx, sudoers and manager configuration. Every regular
archive member was read back and the archive SHA-256 recorded privately;
production service process IDs were unchanged during creation.

## Read-only source comparison

| Component | Matching code/assets | Differing paths present on both servers | Production-only paths |
| --- | ---: | ---: | ---: |
| Suite | 26 | 4 | 0 |
| HP supply | 21 | 4 | 8 |
| HP meter | 32 | 2 | 0 |
| Tektronix | 26 | 0 | 0 |

This inventory compares selected application code and assets, excluding private
configuration and runtime contents. Matching files are not proof of release
enrollment. The counts do not represent whole-server equivalence.

The supply's production-only files include its Classic mobile CSS and branded
icons. All 22 production supply static assets in this comparison match the
public supply source at commit `2a021127d07d9af8ed6e3e829c23f867b80b9850`.
However, both production supply HTML templates differ substantially from those
public templates. The local structural comparison detects changed control-page
JavaScript as well as layout changes; these differences cannot be treated as
cache parameters or copied over without review. Existing server-specific
wrappers and navigation differences also require preservation and reconciliation.

## Template inspection completed

The owner explicitly approved inspection of both production supply templates.
The reviewed source preserves the chart, layout editor, saved preferences,
branding and Classic mobile proportions. Both templates are now staged in the
suite integration source, and the candidate builder overlays them into supply
packages. Ten isolated browser checks and all 204 Linux regression tests passed.
See PRESERVED_SUPPLY_UI_VALIDATION.md for exact hashes and validation limits.

Server-specific wrappers and navigation still need reconciliation. Keep legacy
removal safeguards and bootstrap release gates enabled. Existing-HTTPS attended
enrollment, final clean-card acceptance and production signing remain unfinished.
No production application files or services were changed.
