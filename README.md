# Fischer Instrument Suite

Raspberry Pi web controllers for the HP 6033A power supply, HP 34401A multimeter and Tektronix Ethernet oscilloscope. Install any supported combination and use the shared navigation to switch between instruments.

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

| Controller | Repository | Fresh-install HTTP port |
| --- | --- | --- |
| HP 6033A power supply | [Source and operating guide](https://github.com/RLF62/hp6033a-web-controller) | 8083 |
| HP 34401A multimeter | [Source and operating guide](https://github.com/RLF62/hp34401a-web-controller) | 8082 |
| Tektronix Ethernet oscilloscope | [Source and operating guide](https://github.com/RLF62/tektronix-ethernet-controller) | 8081 |

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

Controllers retain their own source, operating manuals, screenshots and release history. The suite owns signed release coordination and the central ZIP catalog.

## Original ZIP installers

These downloads support the original catalog workflow. They are distinct from the immutable archives selected by the signed updater.

| Installer | Download |
| --- | --- |
| HP 34401A | [meter.zip](approved/packages/meter.zip) |
| HP 6033A | [supply.zip](approved/packages/supply.zip) |
| Tektronix | [scope.zip](approved/packages/scope.zip) |

[Catalog checksums](approved/catalog.json) · [Original standalone installation](STANDALONE.md) · [Original integrated installation](INSTALL.md)

## Validation

All 230 regression tests passed for the signed release. Fresh-card HTTP installation, attended HTTPS production activation, dashboard routes, public artifact verification, backups and a no-op update passed. Settings and credentials were retained. Actual production rollback and unexpected power-loss recovery were not performed; see the acceptance record for limits.
