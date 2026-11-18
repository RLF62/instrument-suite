# Meter-only installation and selected navigation

> This page documents the original source/ZIP installer workflow. For new installations and enrolled updates, start with the [signed suite installer](https://github.com/RLF62/instrument-suite/blob/main/ONE_COMMAND_UPDATER.md). Existing legacy installations need attended migration. Commands below do not replace signed-updater maintenance.


The HP 34401A can run without installing the HP 6033A application. Use Raspberry Pi OS with the `pi` account. Install OS prerequisites `python3-venv`, `python3-pip`, `curl`, and `libusb-1.0-0` first. Extract this repository into a staging folder, then run:

```sh
bash install.sh
```

Choose **Meter only**. The wizard explains its trusted-LAN HTTP mode and asks before installation. It creates `/home/pi/hp34401a`, an isolated Python environment, the `hp34401a` web service on port 8082, and the shared adapter service if one is not already installed. Open `http://CONTROLLER_HOST:8082/`. Classic, Modern, documentation and all meter features use the same backend as the integrated suite. There is no supply dashboard or supply-control API in this host.

This HTTP mode has no password or encryption. Keep it on a trusted LAN; do not port-forward it. For a secured reverse proxy, use the default loopback listener instead:

```sh
python3 standalone_install.py --check
sudo -v
python3 standalone_install.py --apply
```

The noninteractive trusted-LAN equivalent adds `--listen 0.0.0.0` to both commands. `--port` selects an unprivileged port (default 8082). Existing HP HTTPS/authentication settings are untouched. Standalone is a separate local HTTP host; it does not inherit the HP application's login policy.

## Adapter and first use

Fresh hardware configuration is `/home/pi/instrument-suite/config.json`, initially `hardware_enabled:false`, `meter_read_only:true`, `supply_enabled:false`. Enter the cached USB adapter resource and the meter's address; use HP-IB/488 with SCPI on the physical meter. Enable hardware while retaining read-only mode, restart `fischer-gpib`, then verify identity and configuration in the dashboard. After those succeed, allow measurement writes (`meter_read_only:false`), restart the broker and `hp34401a`, verify again and explicitly enable measurements. No installer queries, resets, measurements, output changes or setpoint writes are sent to the instruments.

If a recognized broker is already installed, standalone reuses it without replacing its files or configuration. It refuses an existing supply app that still opens the adapter directly. Do not run an independent VISA controller on the same adapter. Keep acquisition active in only one meter web host at a time when comparing standalone and integrated dashboards.

## Instrument links

Standalone defaults to `{"instruments":["meter"]}` in `/home/pi/hp34401a/tools.json`: no supply/scope/generator links. Optional `--instruments meter,supply,scope,generator` advertises other controllers **already installed** on the same Pi; it does not install them. Missing selected controllers fail preflight. Classic/Modern/documentation and layout controls stay available; hide/show layout preferences remain unchanged. An instrument being powered off does not change navigation.

For the existing integrated host use:

```sh
/home/pi/hp6033a/venv/bin/python install.py --check --instruments meter,supply
/home/pi/hp6033a/venv/bin/python install.py --apply --instruments meter,supply
```

Add `,scope` only after installing the optional Tektronix controller. Integrated selection is stored separately in `/home/pi/instrument-suite/tools.json`. Existing selection is preserved when the option is omitted. Changing links does not disable hardware or remove applications. The scope remains its own Ethernet controller. Its navigation integration is optional and uses the same selected-tool file when installed.

## Update and recovery

Update from a separate extracted source folder using the same check/apply commands. Existing broker configuration is retained byte for byte. The installer keeps a private timestamped backup and manifest under `/home/pi/.instrument-suite-backups/standalone-*` and restores previous app/unit files on activation failure. Read its `ROLLBACK.txt` before manual restoration. Do not start a direct-access controller alongside the broker.

Software and installation checks on the existing test Pi do not establish a fully verified fresh-OS installation. Hardware must be verified after installation. Measurements are not a calibration or accuracy certification.
