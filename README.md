# Fischer Instrument Suite

Raspberry Pi controllers for the HP 6033A power supply, HP 34401A multimeter, and Tektronix Ethernet oscilloscope. Each installed controller shares a menu and an approved catalog for adding standalone instruments.

## Install

Use a separate extracted staging folder on Raspberry Pi OS with the `pi` account. Install `python3-venv`, `python3-pip`, `curl`, and `libusb-1.0-0`, then run:

```sh
bash install.sh
```

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

| Installer | Download | SHA-256 |
| --- | --- | --- |
| HP 34401A Multimeter | [meter.zip](https://github.com/RLF62/instrument-suite/raw/main/approved/packages/meter.zip) | `18b40dd084cd9cb9e2263ec9df71d322b371dd57f158c6f012180c1769424e77` |
| HP 6033A Supply | [supply.zip](https://github.com/RLF62/instrument-suite/raw/main/approved/packages/supply.zip) | `3c1a796617f26f9b1e83263f439e4c9e2f7a2ac775a3e7a4dde13a75950932a0` |
| Tektronix Ethernet | [scope.zip](https://github.com/RLF62/instrument-suite/raw/main/approved/packages/scope.zip) | `cb0e7fd651a11a282ca439e1ae90713cdab41825db6b4c00f1a38a4f977e1e6d` |

[Approved catalog and checksums](https://github.com/RLF62/instrument-suite/blob/main/approved/catalog.json). For the complete installer and manager setup, follow the [Instrument Suite instructions](https://github.com/RLF62/instrument-suite#install).
