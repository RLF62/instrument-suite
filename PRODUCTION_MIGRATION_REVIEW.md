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

## Blocked inspection and next action

The automatic approval review rejected exporting production template contents
and then rejected inspection of limited changed lines after credential-marker
screening. No template content was exported or changed. Explicit permission to
inspect `hp6033a/templates/index.html` and
`hp6033a/templates/classic_dual_preview.html` is required before that review can
continue. Credential files, live configuration, certificates and private keys
are outside this inspection.

Until the production-specific changes are understood, preserve both templates
and do not deploy controller artifacts over them. Keep legacy removal safeguards
and bootstrap release gates enabled. Existing-HTTPS attended enrollment, final
clean-card acceptance and production signing setup remain unfinished.
