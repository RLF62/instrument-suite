# Install and update the three-instrument suite

> This page documents the original source/ZIP installer workflow. For new installations and enrolled updates, start with the [signed suite installer](https://github.com/RLF62/instrument-suite/blob/main/ONE_COMMAND_UPDATER.md). Existing legacy installations need attended migration. Commands below do not replace signed-updater maintenance.


## Components

| Component | Repository | Connection | Installed endpoint |
|---|---|---|---|
| HP 6033A base web controller | RLF62/hp6033a-web-controller | Shared USB–GPIB after meter integration | `/`, `/classic-dual` |
| HP 34401A and adapter broker | RLF62/hp34401a-web-controller | Same broker/socket; unique GPIB address | `/multimeter/classic`, `/multimeter/modern` |
| Tektronix Ethernet controller | RLF62/tektronix-ethernet-controller | Scope Ethernet, separate service | `http://CONTROLLER_HOST:8081/` |

## Meter-only installation

Run `bash install.sh` and choose meter only; see [STANDALONE.md](STANDALONE.md). The supply application is not required. The following steps apply to the integrated suite.

## Fresh integrated installation

1. Install Raspberry Pi OS and use the supported `pi` account for the meter integration. Install the HP base controller from its extracted repository with `bash install.sh`. Follow its HTTP-only/HTTPS and authentication prompts; keep its existing security choices.
2. Extract the meter repository into a separate staging folder. Run `/home/pi/hp6033a/venv/bin/python install.py --check`, review the result, then use `--apply`. The installer backs up before mutations. It does not configure hardware through the adapter.
3. A new `/home/pi/instrument-suite/config.json` defaults to `hardware_enabled: false`, `meter_read_only: true`, `supply_enabled: false`. Enter the adapter resource and unique addresses there. Do not copy another server's config/passwords. The tested addresses were supply 10 and meter 22. Cached adapter USB identity is available with `cat /sys/bus/usb/devices/*/serial`; use the matching Xyphro adapter, not another USB device.
4. For the first connected test, leave `meter_read_only: true`, keep the supply paused if it is absent, set `hardware_enabled: true`, then restart **only** `fischer-gpib`. On the physical meter select HP-IB/488 and SCPI. Use Verify identity & read configuration. This stage does not enable measurement writes.
5. After identity/configuration succeed, set `meter_read_only: false`, restart fischer-gpib and hp6033a, verify identity again, then explicitly Enable measurements. Connect a suitable input and take a single reading before enabling live updates. Confirm the expected function, units and sample age.
6. If the supply is connected, give it a different GPIB address and enable `supply_enabled` in the broker config. Perform the supply's existing connection/output-state checks before remote programming. Never run a standalone direct-VISA controller against this same adapter.
7. Install the optional scope controller from its own repository with `bash install.sh --check`, then `bash install.sh --apply`. Open Setup and enter the scope's own IP address. The Pi address and scope address are different. Do not run competing scope controllers on two Pis at the same time.

## Existing installations and updates

Pause meter/scope acquisition and schedule a web-service interruption. Existing credentials, TLS, presets and runtime configuration stay local. Keep a copy of the installer-created backup path. Review changes, run checks from a separate extracted source directory, then apply.

**Do not run the standalone HP installer/updater over an integrated shared-adapter installation.** Replacing its patched app with a direct-adapter build would violate coordination. The new HP entry points refuse that operation. For an HP base update, stage the new HP app and reapply/validate the meter patch before activation; an automated cross-repository release updater is not yet provided. Meter updates use the add-on installer and retain the current HP app's non-hardware logic. Dashboard layout preferences live in each browser and survive service restarts.

Meter check/apply validates its source and HP patch before stopping services. Existing broker config bytes are retained; new installations start disabled. All validation tests use fakes/mocks. Passing them is not a substitute for connected-instrument verification.

## Rollback

The meter installer prints a private backup directory under `/home/pi/.instrument-suite-backups/`. It contains `backup.tar.gz`, `manifest.json` and `ROLLBACK.txt`. Follow that backup's exact stop/restore/reload/restart commands. Restore files and units together; do not restart a direct-access HP build while a shared broker is still active. A failed activation attempts automatic file/unit restoration and reports whether service recovery succeeded.

The scope installer similarly retains application and user-unit backups and prints their path. Both installers preserve runtime settings and never send reset/output/setpoint commands. Neither changes the live server merely because source is published to GitHub.

## Validation limits

The integration was developed on test `.108`. Do not treat these instructions as permission to deploy to live `.177`. Meter external-trigger pulses, physical Local annunciator behavior, and a full fresh-OS install remain to be verified. Concurrent meter/supply readback and meter-off failure isolation were verified on the live Pi. The scope has its own previously documented hardware evidence. Re-check identity and configuration after any restart.
