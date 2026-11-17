# Add instruments

> This page describes the original approved ZIP catalog. For signed installation and updates, use the [signed suite installer](https://github.com/RLF62/instrument-suite/blob/main/ONE_COMMAND_UPDATER.md). Existing legacy installations need attended migration. Commands below do not replace signed-updater maintenance.


Every dashboard has an **Add instruments** link when the approved catalog is enabled. The same catalog is available from the meter, supply, and scope; it always installs on the Pi hosting that page.

1. Open **Add instruments**.
2. Choose **Install** for an approved controller that is not installed. Installed controllers show **Open**.
3. Watch the progress and log. Only one installation runs at a time.
4. With **Open the tool when installation completes** selected, the page opens the new dashboard automatically. Otherwise use its **Open** button.
5. Configure the instrument connection and verify readback before operating hardware.

Successful installations register themselves and update the navigation in all installed tools. Reload an already-open dashboard to see new links. Instrument power state does not determine whether a controller is installed. Classic/Modern selection and the existing move, resize and hide options remain available.

## Approved catalog

| Controller | New application folder | New-install HTTP port |
|---|---|---|
| HP 34401A | `/home/pi/hp34401a` | 8082 |
| HP 6033A | `/home/pi/hp6033a` | 8083 |
| Tektronix Ethernet | `/home/pi/tektronix-controller` | 8081 |

Existing controllers retain their existing addresses, services and security configuration. For example, an existing supply on the main HTTPS address stays there. The registry records the correct address and port for cross-tool links on that host.

New catalog controllers use trusted-LAN HTTP without login or encryption. Do not expose these listeners to the internet. The catalog honors the existing host application's control authentication when it is enabled. Credentials entered for an installation are sent only to that host and are not saved by the catalog page.

## Coordination and installation boundaries

Meter and supply use the single shared GPIB broker. Installation does not reset an instrument or change its output/setpoints. Existing adapter configuration is preserved. A new adapter configuration starts disabled/read-only; newly added supply access remains disabled until configured. New scope installations require a scope IP in Setup. Installing software is not a hardware connection or accuracy verification.

Packages are local, administrator-approved ZIPs with pinned SHA-256 checksums. The browser accepts only the three approved tool IDs; arbitrary download URLs, scripts, shell commands and service names are not accepted. Dependencies may require internet access. Application preparation and package code run as `pi`. A root-owned activation helper permits only fixed activation, rollback and removal operations for these three services. It never runs package code as root.

Existing app folders/services are not overwritten by the add-tool flow. An installation failure stops and quarantines only the newly created controller and reports the failure; prior controllers are preserved. Interrupted work is reconciled on manager restart.

## Locations and administration

- `/home/pi/instrument-suite/registry.json`: automatically verified controller addresses.
- `/home/pi/.instrument-suite-manager`: installation status, per-job logs and failed-install recovery details.
- `/opt/fischer-suite-manager`: root-owned manager code, approved catalog and package files.
- `fischer-suite-manager.service`: unprivileged manager with a local Unix socket, no separate network listener.
- `/var/backups/fischer-suite-manager`: helper deployment backups and rollback manifest.

Full meter-only distributions containing `approved/catalog.json` enable the helper during setup. To enable it on an existing reviewed installation, run `sudo /usr/bin/python3 -I deploy_manager.py` from the extracted source directory after reviewing its approved packages. Existing supply/scope-only arrangements require the same one-time suite setup. After that, web installation does not need an SSH sudo refresh.

The approved catalog is maintained by updating reviewed packages and their checksums as an administrator. Adding an unreviewed instrument is not a browser feature.

## Remove and reinstall

Installed standalone/catalog controllers offer **Remove** beside **Open**. The confirmation names the controller and defaults to **Keep server settings, presets and captures for reinstall**. Cancel closes it without starting a job. Pause acquisition and disable remote programming before removal. The physical instrument and its output state are not changed.

Removal stops only that controller, archives its application privately, and removes its navigation links. With settings kept, the next catalog installation restores the controller's supported server settings, presets and captures. With the option unchecked, reinstall uses defaults; the private recovery archive remains under `/home/pi/.instrument-suite-manager/removed`. This is not a permanent data-erasure function. Browser appearance/layout preferences and shared adapter configuration are preserved in both cases.

The shared broker is retained. If it uses the selected controller's Python environment, that environment stays in place with a small runtime-only marker. Other applications keep their adapter access, and reinstall reuses the matching environment without upgrading packages beneath the running broker. Therefore a runtime-only folder can remain after removing a dashboard.

Legacy controllers sharing one web service are protected: their Remove button explains that standalone migration is required. The remover does not edit shared application code, authentication or Nginx configuration to split them apart.

If removing the dashboard currently showing the catalog, the page switches to another installed controller for progress. Removing the last dashboard closes web access; the confirmation gives this SSH reinstall command (choose `meter`, `supply` or `scope`):

```sh
python3 /opt/fischer-suite-manager/catalog_cli.py install meter
```

Interrupted removals either restore the stopped controller or finish an already-committed removal. Recovery information and archived service definitions are retained. Do not manually delete a runtime-only folder used by the shared adapter.

## Test evidence

The catalog passed 78 Python tests, including approved-ID validation, package tampering/path rejection, installation admission, existing-service preservation and activation rollback. On the fresh meter-only test Pi, the Tektronix controller was installed from the meter's catalog page, then the supply was installed from the scope's catalog page. Both opened automatically and registered cross-tool links. Shared adapter configuration remained byte-identical. These checks did not enable new supply access or certify measurement accuracy.

On 192.168.1.178, browser removal and reinstall succeeded for the scope and meter, including removal from the meter’s own catalog page. Saved scope, supply and shared adapter configuration remained byte-identical. The broker process stayed unchanged throughout removal and reinstall; its shared Python environment was retained. All three dashboards were restored. A further 22 permission regression checks passed.
