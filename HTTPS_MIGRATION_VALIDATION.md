# Existing HTTPS installation: validation and attended migration

This is development work, not authorization to enroll a working instrument
controller. The public bootstrap remains gated pending release signing and the
remaining connected-instrument acceptance tests. Never run the clean-card
enrollment tool against an existing installation.

## Completed isolated checks

The regression fixture uses a private temporary filesystem and inert service
commands. It exercises the real Linux file activation, backup and restore code
against an existing HTTPS wrapper, presets, authentication files, Nginx files,
systemd units and standard TLS certificate directories. No live server files or
instrument endpoints are used.

An existing HTTPS gateway must have its protected administrator policy. Missing,
unrecognized, writable or symlinked policy blocks before activation. A valid
policy prevents the fresh-install HTTP listener being added. Newly added HP
backends bind to loopback; existing service definitions are retained. Private
backups include `/etc/ssl` and `/etc/letsencrypt` as well as Nginx configuration.
Code rollback preserves the latest private settings and presets.

The TLS fixture runs an ephemeral HTTPS server on loopback with its own generated
certificate and synthetic bcrypt dashboard account. It verifies an existing
six-character password, credential changes, secure HttpOnly/SameSite cookies,
same-origin CSRF validation, and rejection before the fixed-action helper for
invalid passwords, origins or missing CSRF tokens. No extra password store or
minimum twelve-character update password is introduced.

Run on Linux in the development checkout:

```sh
sudo /home/pi/instrument-suite/venv/bin/python -m unittest -v test_https_migration
```

The root filesystem fixture confines every managed path to a fresh temporary
tree and replaces service commands. It must not be adapted to use a live home or
system directory. Normal regression discovery also runs the real TLS tests;
the ownership-sensitive filesystem fixtures explicitly skip when not root.

## Read-only audit

The candidate CLI supports `sudo instrument-suite audit`. It does not download,
enroll, activate, stop or restart anything. It reports unknown software, missing
guard wrappers, non-loopback HTTPS backends, runtime migration requirements and
pending recovery. Unknown version fields remain unknown; folder existence does
not prove an approved version is installed. Audit results do not remove legacy
removal protections or authorize adoption.

## Remaining attended enrollment work

1. Compare the actual production files, services, deployment policy and approved
   component versions. Preserve and review every production-only change.
2. Verify a complete private recovery archive and record which code/service
   files can be restored without replacing current credentials or settings.
3. Prepare permanent hash-locked runtimes alongside existing runtimes. Do not
   move or reinstall a working runtime in place.
4. Stage maintenance wrappers and matching enrollment metadata. The currently
   published candidate deliberately refuses automatic enrollment; a validated
   attended activation transaction is still required.
5. With corrected adapter firmware, verify the supply output OFF and remote
   programming disabled, meter polling/queued operations stopped, and scope
   acquisition stopped/not busy. Use the live HP dashboard for OUTPUT OFF;
   the HP 6033A has no front-panel output ON/OFF button.
6. Acquire verified leases before interruptions. Account for broker service
   dependencies and wait for maintenance HEALTH sockets after service startup.
7. Validate independent updates, failed activation/recovery and the existing
   HTTPS origin. Compare private settings/authentication/certificate hashes and
   unrelated-controller health before declaring migration complete.

No production updater enrollment, new signing identity, stable release or
connected-instrument validation is implied by the isolated fixtures passing.
