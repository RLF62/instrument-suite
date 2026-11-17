# USB-GPIB V2 firmware

Open **USB-GPIB Firmware** from the Instrument Suite dashboard.

1. Pause multimeter acquisition. Turn off the power supply output and disable remote programming before preparing the update.
2. Select **Prepare Firmware Update** and wait for the page to confirm it is ready.
3. Disconnect GPIB from the adapter. Leave USB connected and hold the upper white rectangular button shown in the photo.
4. Select **Write and Verify Firmware** when the page detects the bootloader. Leave USB connected until verification finishes.
5. Disconnect both cables. With USB still unplugged, reconnect GPIB to the powered instrument first, keeping its output off. This may help the adapter leave bootloader mode. Reconnect USB to the same port without holding the button.
6. Select **Verify Version and Resume**.

The updater verifies the firmware before writing, verifies the write afterward, and checks the running version before resuming the controllers.

[UsbGpib V2 manual](https://github.com/xyphro/UsbGpib/blob/master/Tutorials/UsbGpibV2_manual.md#firmware-update-procedure)
