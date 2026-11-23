# Connect an instrument after a signed suite install

A fresh install starts its controllers, but leaves USB-GPIB access disabled. The suite does not know which adapter or instrument is attached. Configure the shared adapter once on the Pi, then enable only the instrument you have connected. The Tektronix Ethernet scope uses its own IP address in Scope Setup instead.

These steps apply to the signed one-line installer on Raspberry Pi OS Bookworm or Trixie. They use the default `pi` account and the HP 6033A power supply as an example. Do not use the older standalone HP 6033A `~/hp6033a` installer or edit only its `gpib_resource` field on a suite installation.

## HP 6033A supply: first connection

1. On the physical HP 6033A, note its HP-IB/GPIB address. The example below uses **10**; use the address actually set on your supply. Turn the output OFF and disable remote programming. Connect the GPIB cable to the instrument **before** connecting the USB-GPIB adapter to the Pi.
2. In SSH on the Pi, discover the adapter's VISA resource. Ignore warnings about optional TCP/IP discovery; use the single `USB...::INSTR` string printed in the tuple:

   ```sh
   sudo /home/pi/instrument-suite/venv/bin/python -c 'import pyvisa; print(pyvisa.ResourceManager("@py").list_resources("USB?*::INSTR"))'
   ```

   If no USB resource appears, check `lsusb`, reconnect the adapter after the installer-created udev rule is in place, and rerun the command. Never copy another Pi's adapter serial number.

3. Open the shared adapter configuration:

   ```sh
   sudo nano /home/pi/instrument-suite/config.json
   ```

   Set `resource` to **your** complete VISA string; set `addresses.supply` to the physical supply's address; set `hardware_enabled` and `supply_enabled` to `true`. For a supply-only installation, leave `meter_read_only: true` and `generator_enabled: false`. This excerpt illustrates the fields; preserve the other entries already in the file:

   ```json
   {
     "resource": "USB0::1003::8293::YOUR_ADAPTER_SERIAL::0::INSTR",
     "addresses": {"supply": 10, "meter": 22, "generator": 20},
     "hardware_enabled": true,
     "meter_read_only": true,
     "supply_enabled": true,
     "generator_enabled": false
   }
   ```

   In nano, press Ctrl+O, Enter to save, and Ctrl+X to exit. JSON uses lowercase `true` and `false`, double quotes, and commas between fields.

4. Restart the **shared adapter broker only**, then open the supply page printed by the installer:

   ```sh
   sudo systemctl restart fischer-gpib
   ```

   In the supply dashboard, confirm **GPIB: CONNECTED**, output OFF, and live voltage/current readbacks that agree with the physical front panel. It may take a refresh for a busy adapter to finish its first read. You can also check readback without sending a control command:

   ```sh
   curl -fsS http://127.0.0.1:8083/api/status | python3 -m json.tool
   ```

   Look for `"gpib_connected": true`, `"gpib_status": "CONNECTED"`, and `"remote_control_enabled": false`. If the output is ON or unknown, stop and check the physical instrument before enabling remote controls. The browser's **ENABLE REMOTE** action is separate; configuration and status checks do not authorize output or setpoint writes.

## Other instruments

| Instrument | Connection setting | First check |
| --- | --- | --- |
| HP 34401A meter | Use its distinct HP-IB address in `addresses.meter` in the same shared config. Start with `meter_read_only: true`. | Select HP-IB/488 and SCPI on the meter, then use its identity/configuration verification before enabling measurements. |
| HP 33120A generator | Use its distinct address in `addresses.generator`; keep `generator_enabled: false` until connected and ready for attended verification. | Verify identity and configuration in the generator controller before Apply. |
| HP 5385A counter | Use its own address and enable its access only when connected. | Verify identity/readback in the counter controller before controls. |
| Tektronix Ethernet scope | In the scope dashboard's **Setup**, enter the scope's Ethernet IP address or hostname. | Use **Test Connection**; it does not use the USB-GPIB adapter. |

Only one broker should own a USB-GPIB adapter. GPIB addresses on a shared bus must be unique. The address values in the example are placeholders for equipment other than the supply; inspect each instrument's physical settings. Leave absent devices disabled. The installer cannot infer these settings safely and does not issue instrument commands during installation.

If the supply stays disconnected, check the adapter resource and address in `config.json`, verify the adapter is attached with `lsusb`, and inspect `sudo journalctl -u fischer-gpib -n 60 --no-pager`. Do not run a separate standalone direct-VISA controller on this adapter.
