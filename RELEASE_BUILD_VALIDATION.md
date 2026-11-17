# Signed release builder (development validation)

`tools/build_release.py` builds artifacts; it never enrolls the updater, installs dependencies, contacts instruments, changes authentication, starts services, or publishes to GitHub. Run it as an ordinary user. The private test-candidate builder remains available for fixtures; its historical source labels must not be used as public release provenance.

## Required inputs

Prepare separate clean Git checkouts of the reviewed Instrument Suite, HP 6033A, HP 34401A, and Tektronix source commits. Each checkout must have the expected RLF62 origin URL and no modified or untracked files. Select and review the actual commits before building: checking a local origin URL is not independent proof that a commit was approved or published by GitHub.

Provide four reviewed target-platform wheel lock files named suite.lock, supply.lock, meter.lock and scope.lock, plus a JSON file mapping all four names to explicit component versions. A lock permits exact package versions and SHA-256 hashes only. URLs, pip directives, empty locks and duplicate package names are rejected. Generate the locks on the target Raspberry Pi OS/Python architecture with the existing lock_requirements.py tool and review the resolved packages.

Keep the signing private key, its pinned public key, versions file, lock directory, and output outside the source checkouts. Never commit a signing private key. Existing development test keys are not production trust keys. Key custody and authenticated distribution of the public key still require release approval.

Example maintainer command (replace all paths and approved versions):

```sh
python3 tools/build_release.py \
  --suite /release-src/instrument-suite \
  --supply /release-src/hp6033a-web-controller \
  --meter /release-src/hp34401a-web-controller \
  --scope /release-src/tektronix-ethernet-controller \
  --locks /release-inputs/locks \
  --versions /release-inputs/versions.json \
  --release v1.0.0 --sequence 1 \
  --key /private-signing/release.key \
  --public-key /release-inputs/release.pub \
  --output /release-output/v1.0.0
```

The version file has the form:

```json
{"suite":"v1.0.0","supply":"v1.0.0","meter":"v1.0.0","scope":"v1.0.0"}
```

These are illustrative versions, not a declaration of an approved release or an instruction to reuse an existing tag. Review component version increments, suite compatibility, sequence and availability of the target release asset URLs before publication. The initial builder builds all four artifacts; the installed update engine still selects which components need installation. A later release with unchanged components needs its manifest and compatibility relationships reviewed to avoid unnecessary replacements.

## Build protections

- Source commit IDs come from the actual clean checkouts, replacing historical hard-coded labels.
- Every selected input must be tracked, match committed bytes, satisfy the existing managed-file/private-path policy, and remain unchanged through packaging. Selected ignored files and source symlinks are rejected.
- The signed manifest includes source repositories, commit IDs, per-file source hashes, dependency-lock hashes, artifact hashes/sizes, component versions, and the supply's suite-overlay commit.
- The supply uses the reviewed suite shared-adapter transformation and preserved Classic/Modern templates from the staged suite snapshot.
- Tar metadata and gzip timestamps are normalized. The manifest intentionally includes current issuance and expiration timestamps.
- Signing uses Ed25519 through OpenSSL and immediately verifies the result against the supplied public key.
- Artifacts stage in a temporary sibling directory. Failures leave no completed output directory. Existing output is rejected; the tool does not overwrite prior releases.
- The manifest expires after 30 days. Publishing and future refresh of authenticated metadata are separate release operations.

The source/private-path policy does not replace a human credentials review, dependency approval, or independent confirmation of source commits. No real production key or release was created during testing.

## Validation and remaining gates

Ten isolated tests use actual Git repositories and temporary Ed25519 keys. They cover a complete signed build and preserved supply templates; modified and untracked source; unexpected repository identity; ignored managed files; unsafe, empty or duplicate dependency locks; existing output preservation; mismatched signing keys and cleanup; keys/output inside source trees; invalid versions/sequences; and a source change during packaging.

The complete regression suite passed on development .108: 217 tests in 18.368 seconds, exit status 0. No live services or instrument settings changed.

The existing-HTTPS attended enrollment implementation, production signing-key custody and authenticated bootstrap pinning, approved real release builds, fresh-card acceptance and production deployment remain unfinished. This tool does not remove any of those gates.


## Real repository-source package check on .108

After the fixture tests, clean public GitHub checkouts were downloaded at:

| Component | Source commit |
| --- | --- |
| Suite development branch | b684c4f1b76790410f4bdd325446650bcf6e737f |
| HP 6033A | 2a021127d07d9af8ed6e3e829c23f867b80b9850 |
| HP 34401A | 754066c340c0f200bf2db5784feba4b3c7a5f8d3 |
| Tektronix | e9a338e7869e01376a2a4161180821e045f9365c |

All four published requirements files resolved successfully into exact wheel/hash locks on aarch64 Raspberry Pi OS with Python 3.13.5. No dependency was installed into a live controller environment during this check.

The CLI builder then completed a full four-component build with a newly generated private TEST_ONLY Ed25519 key and synthetic version v0.1.99. These are private validation artifacts, not an approved release, and must never be uploaded to public releases or used to enroll a production updater.

A separate inspection verified the signed manifest, all four archive sizes and SHA-256 values, safe extraction, and the existing payload file policy. All 88 Python files across the four extracted packages compiled without importing or executing controller applications. Both supply HTML templates matched the approved production-source SHA-256 values exactly, and the Classic mobile CSS was present.

Private test manifest SHA-256: 020d8cf426c56d49dd14553ec99b26ee15e8984112277808525186fc743d6b45.

This verifies real-source packaging on .108, not dependency installation in a fresh runtime, running-service activation, fresh-card installation, or production enrollment. The private test key, generated packages, machine-specific lock files and local logs were not published.
