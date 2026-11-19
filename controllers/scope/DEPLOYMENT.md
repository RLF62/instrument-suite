# Deployment and verification

## Current installation

Use the [signed suite installer](https://github.com/RLF62/instrument-suite/blob/main/ONE_COMMAND_UPDATER.md) for a fresh installation and `sudo instrument-suite update` for enrolled systems. Scope v0.3.3 is selected by the suite v1.0.5 signed manifest. [Current acceptance](https://github.com/RLF62/instrument-suite/blob/main/FRESH_CARD_VALIDATION.md) covers fresh-card HTTP and attended HTTPS suite activation.

The scope listener remains trusted-LAN HTTP port 8081, independently of the supply/meter HTTPS gateway. Configuration, channel colors, measurement selections, personal presets and capture files remain local.

## Service ownership

Signed suite installations manage a system service. Use:

```sh
sudo systemctl status tektronix-controller
sudo journalctl -u tektronix-controller -n 60 --no-pager
```

The original `install.sh` workflow installs a user service instead. For that workflow:

```sh
systemctl --user enable --now tektronix-controller.service
sudo loginctl enable-linger USERNAME
systemctl --user status tektronix-controller.service
```

Replace `USERNAME` with the service account. Do not install or start both service arrangements on the same port. Keep one Gunicorn worker; controller requests serialize instrument transactions. Different hosts do not share this lock, so only one host should own the scope.

## Verification and recovery

See the [operating reference](README.md) for offline test commands and the opt-in hardware-test warning. Signed maintenance requires acquisition stopped and BUSY false; it never issues a stop/reset command to satisfy that check.

Use `sudo instrument-suite backup` and `sudo instrument-suite rollback --dry-run` for suite backup/recovery. Original user-service installations use the backup and recovery instructions printed by their installer.

[Earlier deployment evidence](docs/DEVELOPMENT_HISTORY.md) is historical. Connected verification included identity, original/display PNGs, channel CSVs, measurements, presets, capture bundles, bounded communication failure and recovery. Physical Android touch behavior and Sony recipes remain unverified. Screenshots are illustrative snapshots.
