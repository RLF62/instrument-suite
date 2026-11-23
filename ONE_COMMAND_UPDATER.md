# One-command installation and maintenance

The stable signed release channel is published and verified. Fresh-card HTTP
installation and attended enrollment of an existing HTTPS deployment passed.
See [FRESH_CARD_VALIDATION.md](FRESH_CARD_VALIDATION.md) for the acceptance record.
Existing legacy installations require the attended migration procedure; the
bootstrap refuses to overwrite an installed updater.

## Public interface

```sh
curl -fsSLO https://raw.githubusercontent.com/RLF62/instrument-suite/main/bootstrap.sh
sudo bash bootstrap.sh
sudo instrument-suite status
sudo instrument-suite check
sudo instrument-suite install --instruments meter,scope
sudo instrument-suite update --dry-run
sudo instrument-suite update
sudo instrument-suite configure-catalog
sudo instrument-suite backup
sudo instrument-suite rollback --dry-run
sudo instrument-suite rollback
```

`--help` describes the commands. An interactive fresh installation asks which
controllers to install. Noninteractive installations specify `--instruments`.
The existing reviewed installers currently require the `pi` account and
`/home/pi`. The installer checks Raspberry Pi hardware, ARM architecture,
dependencies and disk space. Fresh bootstrap identifies Bookworm/Python 3.11
or Trixie/Python 3.13 before downloading the release. After installing OS
prerequisites, it verifies the signed wheels for every selected controller
before enrolling the updater or changing controller services. A missing wheel
or hash fails with the existing installation intact; package versions and
hashes remain pinned. The signed locks contain reviewed 64-bit ARM wheels for
both Python versions. At least 512 MiB plus the estimated backup size
must be free; dependencies may require more space.

After the installer succeeds, use [Connect an instrument](GPIB_SETUP.md) to discover
the local adapter resource, set unique GPIB addresses and enable only connected
instruments. The HP 6033A supply-only steps include exact commands and a
read-only verification. These settings are not entered in the suite dashboard.

The shared dashboard uses port 8080. Independent controllers retain ports 8081
(scope), 8082 (meter), and 8083 (supply). Fresh installation uses trusted-LAN
HTTP. Existing TLS, authentication and deployment wrappers are preserved;
unrecognized or legacy installations require attended enrollment and are never
silently adopted. No legacy removal protection is disabled by this updater.
The generator connection starts disabled on a fresh installation. After the adapter
and GPIB address are configured and identity/readback succeed, enabling the
generator connection makes Apply available without a second read-only setting.
Apply still requires a fresh configuration token and explicit confirmation.

## Release trust and independent versions

The GitHub stable-release API is discovery only. A canonical manifest must have
a valid detached Ed25519 signature under an administrator-pinned public key.
It names immutable versioned assets from the four existing repositories,
component versions, source commits, SHA-256 hashes, lengths and minimum compatible
versions. A validity window and persistent sequence counter reject expired,
future and replayed metadata. Software rollback does not lower the sequence
counter. A checksum from the download server alone does not authorize anything.

Use `tools/lock_requirements.py` on the target Pi OS/Python architecture to
prepare reviewed wheel-only dependency locks. The installer invokes pip as `pi`
with `--require-hashes --only-binary=:all:` in permanent isolated runtimes. It
never runs controller packages or package installation scripts as root.

Controller source and new release archives live in instrument-suite. Historical
signed manifests still reference the earlier controller repositories; their
assets remain available for recovery. Existing installations must install the
transition release before accepting a suite-only controller asset manifest.
The suite manifest selects compatible component versions. A meter-only update downloads and
restarts the meter only; shared-runtime changes require safety checks for all
affected controllers. New component types require a reviewed adapter/specification,
not a replacement of the transaction engine.

## Safety and recovery

Before interruption, the root engine holds a local maintenance lease. The lease
blocks new requests, drains active requests and verifies the instrument state.

- Supply: the existing read-only shared-broker path must return output OFF,
  and the controller must report remote programming disabled. Missing connection
  or an unknown value blocks maintenance. The updater never switches output.
- Meter: polling must be paused, no controls may be queued, and the operation
  mutex must be idle.
- Scope: the serialized read-only path must confirm acquisition stopped and
  BUSY false. If it cannot, the user must stop acquisition and retry. No reset,
  stop, autoset or programming command is sent by the updater.

A durable journal and maintenance gate keep controls locked across failed
activation or unexpected restarts. Staged files are verified before interruption.
Private backups include applications, settings, authentication, certificates,
systemd and Nginx configuration. Per-file code backups have hashes. Code rollback
preserves the latest private settings, restores dependencies and service definitions,
and validates service startup. The complete private archive is available for an
attended administrator recovery; do not blindly extract it over a working host.

If recovery cannot be verified, the journal/gate remain and the command reports
the recovery directory. Run `sudo instrument-suite rollback` from a terminal;
the dashboard is not required. Supply rollback still requires a verifiable safe
state. Do not start an unpatched direct-GPIB app alongside the shared broker.

## Local candidate validation

`tools/build_candidate.py` reuses the reviewed central ZIPs and transforms the
supply using the existing tested shared-adapter patch. It prepares local signed
test artifacts only and never uploads to GitHub. Candidate signing keys stay
outside the repository and are not the future public release signing identity.
`tools/enroll_candidate.py` refuses an occupied test card. The explicit
`maintenance.candidate` entry point verifies a root-pinned local signature and
artifact hashes before using the same engine as the public CLI. This offline
test path is not a public update channel or a web-helper argument.

## Web-update authorization

Fresh installation offers disabled web updates, explicit password-free trusted-LAN
HTTP updates, or reuse of an HTTPS dashboard login. No separate update password is
created, and there is no 12-character minimum applied to an existing dashboard
password. Terminal commands use Linux sudo authorization only.

For a trusted-LAN HTTP installation, an administrator can explicitly configure:

```sh
sudo instrument-suite configure-web-updates --mode trusted-lan \
  --trusted-lan 192.168.1.0/24 --origin http://192.168.1.108:8080
```

These are examples; choose the actual trusted subnet and exact dashboard origin.
Only private RFC1918/ULA CIDRs are accepted. Host/origin validation, same-origin
JSON requests, CSRF tokens and SameSite cookies are required. Client addresses
are taken directly from the connection or from sanitized headers supplied by an
explicit local reverse proxy. Arbitrary forwarded headers are not trusted.

HTTPS mode uses `--mode dashboard`, an HTTPS `--origin`, and
`--dashboard-credentials` pointing to the existing dashboard bcrypt htpasswd file.
That file is read for verification and is never replaced. The root-owned web policy
is preserved on upgrade; changing it requires an explicit administrator command
with `--replace-policy`. No existing dashboard authentication is automatically
disabled. A known HTTPS gateway cannot acquire a password-free HTTP side door.

The Software Updates page uses an asynchronous fixed-action root helper for
Check, Update, Backup and Rollback. The helper accepts no shell commands, paths,
passwords or download URLs. It calls the same CLI engine and all integrity,
instrument-safety and recovery checks remain mandatory. Status/progress and
errors are available while a job is running. During local candidate validation,
public update discovery reports that a signed public release is still required.

## Validation and release maintenance

The isolated maintenance tests exercise signature verification, replay/expiry,
unsafe archives, dependency compatibility, independent updates, one/two/three
controller plans, low space, interrupted download, activation failure, recovery,
quiescence, dry runs and concurrent-operation locks. These simulated tests do not
substitute for a clean-card installation, hardware interlocks or a power-loss test.
The stable release uses a pinned production signing identity and immutable assets
in the respective repositories. Release metadata expires: maintainers must publish
new signed metadata before expiry; changing the clock or skipping signature checks
is not a recovery procedure.

## Existing Unix-socket HTTPS gateways

The web authorization policy requires a verified connection address. An existing
Unix-only Gunicorn gateway needs a local TCP listener for the update API. Retain
the original Unix listener, add a loopback-only listener, and route only the exact
`/api/software-updates` location to that listener. The HTTPS proxy must overwrite
`Host`, `X-Real-IP` and `X-Forwarded-Proto` with its own verified values. Keep the
existing LAN restrictions and dashboard credentials. Do not bind this listener to
all interfaces or trust client-supplied forwarding headers. Back up the deployment
configuration and validate Nginx before reloading it. The updater preserves these
host-specific service and proxy settings.

## v1.0.2 catalog-manager setup

Fresh signed installations configure the corrected Add/Remove Instruments helper
automatically. This setup starts or refreshes only the manager; controller,
gateway and broker services are preserved.

An updater upgrading from v1.0.1 runs its old activation engine for that first
transaction. After the update, perform the one-time verified helper refresh:

```sh
sudo instrument-suite update && sudo instrument-suite configure-catalog
```

`configure-catalog` downloads and verifies the suite through the pinned signing
key before privileged setup. It does not execute files from a mutable source
checkout. It keeps a private helper/service/sudoers backup and restores them if
setup fails. Run `sudo instrument-suite configure-catalog --dry-run` to inspect
the selected release without changing services. Existing manually corrected
managers can use the same refresh. No instrument removal is performed by setup.

The corrected manager recognizes the exact generated maintenance wrapper on
independent controller services. Enrolled removals use the instrument safety
lease and shared lock; reinstall uses signed archives and the selected retained
settings. Unknown/shared legacy services remain protected.
