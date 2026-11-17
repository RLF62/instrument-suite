# Fischer Instrument Suite

Raspberry Pi controllers for the HP 6033A power supply, HP 34401A multimeter, and Tektronix Ethernet oscilloscope. Each installed controller shares a menu and an approved catalog for adding standalone instruments.

## Install

On a fresh Raspberry Pi OS installation with the `pi` account, use the signed installer:

```sh
curl -fsSLO https://raw.githubusercontent.com/RLF62/instrument-suite/main/bootstrap.sh
sudo bash bootstrap.sh
```

After installation, use `sudo instrument-suite check` and `sudo instrument-suite update`.
See [ONE_COMMAND_UPDATER.md](ONE_COMMAND_UPDATER.md) for supported platforms,
web maintenance, instrument safety and recovery. Legacy installations require
attended migration before enrollment.

The original ZIP installers remain available below. Extract each into its own
staging folder and follow its included installation instructions.

Choose the meter-only installation or integration with an existing HP 6033A controller. The meter-only path can enable the included, checksum-verified instrument catalog. Read [STANDALONE.md](STANDALONE.md), [INSTALL.md](INSTALL.md), and [CATALOG.md](CATALOG.md) before activation.

## Shared menu and removal

Successful installers request registration with the local manager. Verified installed tools appear in every controller's menu, using the current browser host and each controller's configured protocol and port. A missing or busy manager reports registration as pending without failing the controller installation.

Standalone catalog installations support individual removal and reinstall while retaining settings. Existing integrated or legacy services remain protected: they must be migrated before their Remove buttons can be enabled. Installing the manager does not perform that migration.

New standalone controllers use trusted-LAN HTTP and begin with GPIB access disabled. Existing secured installations retain their configuration and authentication. Installation and registration do not reset or program the physical instruments.

## Validation

- 86 suite Python tests, 59 supply-installer tests, and 26 Tektronix tests passed.
- Five shared-menu and seven Tektronix frontend checks passed with Node.
- All three controllers completed removal and fresh application reinstall on the install-test Pi; the other controllers remained available with unchanged application files.
- The existing production installation retains its shared/legacy removal protections.

Bare-card operating-system installation and hardware commissioning are separate from application install validation.

## Individual projects

- [HP 6033A](https://github.com/RLF62/hp6033a-web-controller)
- [HP 34401A](https://github.com/RLF62/hp34401a-web-controller)
- [Tektronix Ethernet](https://github.com/RLF62/tektronix-ethernet-controller)

## Verified installer downloads

The three installers are maintained in the central repository:

| Installer | Download |
| --- | --- |
| HP 34401A Multimeter | [meter.zip](https://github.com/RLF62/instrument-suite/raw/main/approved/packages/meter.zip) |
| HP 6033A Supply | [supply.zip](https://github.com/RLF62/instrument-suite/raw/main/approved/packages/supply.zip) |
| Tektronix Ethernet | [scope.zip](https://github.com/RLF62/instrument-suite/raw/main/approved/packages/scope.zip) |

[Approved catalog and checksums](https://github.com/RLF62/instrument-suite/blob/main/approved/catalog.json). For the complete installer and manager setup, follow the [Instrument Suite instructions](https://github.com/RLF62/instrument-suite#install).

## Independent services behind HTTPS

The shared suite now includes the gateway and deployment-policy support used to separate legacy controllers while preserving existing HTTPS URLs and control authentication. After a completed migration, each controller can be removed and reinstalled without taking down the suite or the other instruments. See the [gateway and migration guide](https://github.com/RLF62/instrument-suite/blob/main/GATEWAY_MIGRATION.md). Existing legacy installations still require an attended migration; installing the catalog alone does not perform it.


## Dashboard icons

The controller includes local favicon sizes 16, 32 and 48 px, an Apple touch
icon at 180 px, and Android home-screen icons at 192 and 512 px. Icons and the
web app manifest use same-origin paths for HTTP and HTTPS. The two HP
controllers use the existing HP artwork; the Tektronix controller uses the
supplied Tektronix artwork. Browser tab icons may need a hard refresh after
upgrading. Existing Android shortcuts may need to be added again.

The shared suite and standalone installers retain these assets. Icon updates
do not change instrument configuration or issue instrument commands.


## Signed maintenance

[Stable signed releases](https://github.com/RLF62/instrument-suite/releases/latest)
provide independent controller versions, signature and dependency verification,
instrument interlocks, backups and rollback. HTTPS web updates reuse the existing
dashboard credentials; trusted-LAN HTTP installations can explicitly enable
password-free updates. Terminal maintenance uses sudo.

The [acceptance record](FRESH_CARD_VALIDATION.md) includes 230 regression tests,
fresh-card installation and attended HTTPS production activation. A rollback
preview passed; an actual production rollback and a power-loss test were not performed.
