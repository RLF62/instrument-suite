# Fischer Instrument Suite

Raspberry Pi web controllers for the HP 6033A power supply, HP 34401A multimeter, Tektronix Ethernet oscilloscope and HP 33120A function generator. Install any supported combination and use the shared navigation to switch between instruments.

## Install and update

For a fresh Raspberry Pi OS installation with the `pi` account, use the signed suite installer and select the controllers you want:

```sh
curl -fsSLO https://raw.githubusercontent.com/RLF62/instrument-suite/main/bootstrap.sh && sudo bash bootstrap.sh
```

For installations already enrolled in the signed updater:

```sh
sudo instrument-suite check
sudo instrument-suite update --dry-run
sudo instrument-suite update
```

[Installation and recovery guide](https://github.com/RLF62/instrument-suite/blob/main/ONE_COMMAND_UPDATER.md) · [Stable signed release](https://github.com/RLF62/instrument-suite/releases/latest)

HTTPS web maintenance reuses the existing dashboard credentials. Trusted-LAN HTTP installations can explicitly enable password-free updates. Terminal maintenance uses sudo. Existing legacy installations require [attended migration](https://github.com/RLF62/instrument-suite/blob/main/GATEWAY_MIGRATION.md); the bootstrap does not overwrite an enrolled updater.

## Controllers

| Controller | Source in this repository | Fresh-install HTTP port |
| --- | --- | --- |
| HP 6033A power supply | [controllers/supply](controllers/supply) | 8083 |
| HP 34401A multimeter | [controllers/meter](controllers/meter) | 8082 |
| Tektronix Ethernet oscilloscope | [controllers/scope](controllers/scope) | 8081 |
| HP 33120A function generator | [controllers/generator](controllers/generator) | 8084 |

The fresh suite dashboard uses port 8080. Existing HTTPS installations retain their configured URLs and authentication. Navigation uses the current browser host. Supply and meter share one adapter broker; do not run a direct-adapter application against that same adapter.

## Maintenance and recovery

Signed manifests select compatible, independently versioned controller packages. Downloads and dependency locks are verified before activation. Instrument interlocks, private backups and automatic recovery remain mandatory.

Before maintenance, confirm supply output OFF and remote programming disabled, pause meter polling, and stop scope acquisition. Missing or unknown instrument state blocks the operation. The updater does not change those instrument states for you.

```sh
sudo instrument-suite status
sudo instrument-suite backup
sudo instrument-suite rollback --dry-run
```

After reviewing the preview, `sudo instrument-suite rollback` performs recovery. Keep private backup archives and credentials off GitHub.

## Documentation

- [Documentation index](DOCUMENTATION.md)
- [Signed installation, web updates and recovery](ONE_COMMAND_UPDATER.md)
- [Existing HTTPS migration](GATEWAY_MIGRATION.md)
- [Add/remove instruments and approved catalog](CATALOG.md)
- [Current acceptance record](FRESH_CARD_VALIDATION.md)

All controller source, operating manuals and screenshots live in this repository. New controllers should be added under `controllers/<name>` and enrolled in the signed suite manifest. New signed release archives are published together on the suite release. Historic signed releases still refer to immutable assets in the earlier controller repositories; keep those assets available for recovery.

## Original ZIP installers

These downloads support the original catalog workflow. They are distinct from the immutable archives selected by the signed updater.

| Installer | Download |
| --- | --- |
| HP 34401A | [meter.zip](approved/packages/meter.zip) |
| HP 6033A | [supply.zip](approved/packages/supply.zip) |
| Tektronix | [scope.zip](approved/packages/scope.zip) |
| HP 33120A | [generator.zip](approved/packages/generator.zip) |

[Catalog checksums](approved/catalog.json) · [Original standalone installation](STANDALONE.md) · [Original integrated installation](INSTALL.md)

## Validation

The four-controller suite ran 269 regression tests successfully, with 21 expected skips in the unprivileged run. The preceding 237-test removal-manager build also passed with root privileges. Public v1.0.2 signature verification and all four archive/hash/length checks passed; controller archives are unchanged.

Fresh-card HTTP installation, attended HTTPS production activation, backups and a no-op update passed for the earlier baseline. The v1.0.2 real removal/reinstall test on spare hardware is still pending. Actual production rollback and unexpected power-loss recovery were not performed; see the acceptance record for limits.

When upgrading from v1.0.1, run the one-time verified helper setup after updating:

```sh
sudo instrument-suite update && sudo instrument-suite configure-catalog
```

Fresh v1.0.2 bootstraps configure the helper automatically.

## USB-GPIB V2 firmware maintenance

The suite landing page includes an attended [USB-GPIB firmware updater](GPIB_FIRMWARE.md) with pinned firmware verification, application/EEPROM backups, readback checks, recovery gates and running-version verification. The complete attended update was verified on a Raspberry Pi test installation: firmware write/readback, unchanged EEPROM, physical power cycle, V2.5 runtime verification, controller restart and cleared maintenance gates.
