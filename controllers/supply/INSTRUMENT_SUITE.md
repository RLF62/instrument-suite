# Instrument Suite installation and maintenance

The current cross-controller installer, signed release selection and recovery engine live in [Fischer Instrument Suite](https://github.com/RLF62/instrument-suite).

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

## Shared adapter and services

Supply and meter share one USB-GPIB broker with unique instrument addresses. Each web controller runs independently. Do not run the original direct-VISA supply build alongside the broker.

The suite retains existing instrument settings, credentials and host-specific HTTPS URLs. Fresh hardware access starts disabled and requires deliberate connection setup and identity/state verification.

## Guides

- [Signed maintenance and safety interlocks](https://github.com/RLF62/instrument-suite/blob/main/ONE_COMMAND_UPDATER.md)
- [Attended HTTPS migration](https://github.com/RLF62/instrument-suite/blob/main/GATEWAY_MIGRATION.md)
- [Original integrated installer reference](https://github.com/RLF62/instrument-suite/blob/main/INSTALL.md)
- [Current acceptance and limits](https://github.com/RLF62/instrument-suite/blob/main/FRESH_CARD_VALIDATION.md)

The original standalone `update.sh` does not update an integrated shared-adapter installation. Use the suite updater after enrollment.
