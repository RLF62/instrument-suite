# Historical Tektronix development and validation notes

These are stage-specific records from earlier versions. Statements about pending deployment, installer availability, service type or repository visibility describe that stage only. Use the current [README](../README.md), [deployment guide](../DEPLOYMENT.md) and [suite acceptance record](https://github.com/RLF62/instrument-suite/blob/main/FRESH_CARD_VALIDATION.md) for current status. Private deployment backup locations have been omitted.

## Baseline and verification

Offline checks cover measurement sentinels, signed sample and nonzero-offset scaling, envelope pair timing, truncated block restoration, restoration failures, timeout lock release, connection validation, and selective image recoloring. Run:

    ~/tektronix-controller-venv/bin/python -m unittest -v test_scope_io test_screen_effect

verify_live.py is an opt-in hardware test script: it temporarily changes channel, acquisition and trigger settings, exercises exports and presets, then restores its snapshot. It must not be run while preserving an in-progress acquisition. Do not run it automatically on installation.

Connected checks completed: both channel CSVs and SI scaling; invalid/off-channel measurements; exact transfer/immediate-setting restoration; continuous/stopped/armed-Single exports; Single waiting/triggered/stopped states; acquisition/channel settings; preset save/recall; Menu Off while armed; concurrent request serialization; offline Setup; configuration persistence across service restart. Additional connected checks passed: mixed-channel measurement entry save/remove/readback, four-slot application with rejection of a fifth, Autoset status/settings/image readback, and paired original/effect captures. On an actual two-channel capture, 8474 trace pixels and 2603 channel-text pixels changed color while 296123 other pixels remained byte-for-byte equal in RGB. Eleven offline regression tests pass.

Future work: a shared instrument dashboard linking Tektronix, HP 6033A, HP 34401A, HP 33120A and HP 5385A. It is not part of this standalone scope build.

## Reference

Tektronix Programmer Manual 071-0381-03:
https://download.tek.com/manual/071038103web.pdf

Relevant sections: immediate measurement DATA/type/source/units, WAVFRM?/WFMPRE?/CURVE?, acquisition state/stop-after, channel controls, display palette, MEAS1â€“MEAS4 display slots, and CLEARMENU.

## v0.2.1 image refresh fix

Automatic screen refresh now requests only the image. Acquisition status updates independently; control inputs are refreshed only at page startup, Read settings, or after an explicit control action. Front-panel changes require Read settings. Optional measurement refresh updates its readouts only.

Background refresh does not disable controls. Foreground actions cancel/supersede pending background image requests and have their own ordered queue. This does not bypass the server instrument lock: hardware traffic remains serialized.

Each new displayed frame is decoded before replacing the old image. Old image URLs are released after the replacement has painted. The last valid image remains visible on capture failure, and superseded background frames cannot overwrite a more recent user action.

Five Node-based regression scenarios cover image-only polling, foreground priority/ordering/error recovery, decoded-frame handoff and URL lifetime, stale-frame suppression, and original-image success/failure handling. Run `node test_refresh.js` from the source folder. Desktop and narrow mobile layouts were inspected in the browser; physical Android touch operation remains unverified.

The prior application was backed up before deployment.


## v0.3.0 operating guide and documentation

The local HTML portal at /docs/ separates the operating guide from advanced technical, API, installation and recovery references. Styling, script and five actual dashboard/Setup/detail screenshots are served locally. Screenshots enlarge in a keyboard-dismissible dialog. Links use relative paths/current host. The original complete technical reference remains at /docs/reference.md.

### Measurement quality and freshness

Matching on-screen measurement slots are read directly; other entries use immediate measurements. Images and readings still arrive sequentially and can disagree during changing or noisy signals. Low-signal warnings are retained with uncertain values rather than automatically rejected. The connected CH2 low-amplitude frequency was visibly unstable; this correction does not make an unreliable frequency accurate.

Images and measurement lists show their last successful update. Failure retains the previous result with stale styling. Automatic updates delayed over 30 seconds are also marked stale. Manual snapshots retain their age label.

### Capture bundle

/api/capture-bundle collects original/effect PNGs, both available channel CSVs, measurements.json, settings.json and manifest.json. Disabled/unavailable channels produce an explanation and a partial manifest rather than invented CSV samples. Transport failure aborts. Collection is sequential and sends no acquisition-state writes: it is not a simultaneous test snapshot. Old-stored-record and host-time warnings are included.

Connected verification collected a complete ZIP with both 10,000-sample channel CSVs, valid ZIP integrity, images and settings. Acquisition remained running with RUNSTOP before/after. Existing waveform helper verifies transfer-setting restoration. No physical scope settings were deliberately changed for screenshots or this bundle check.

### Controller setup backup and restore

Setup exports a versioned JSON containing connection/timeout, channel colors, saved measurement selections and personal presets. Review validates all settings before restore. The reviewed current-preference fingerprint prevents restoring against changed preferences. Before replacement an automatic backup is saved in setup-backups/ and downloadable. A failed multi-file write restores original file bytes or absence; regression tests inject a failure to verify rollback.

Connected HTTP checks verified an identical-preference restore, prior-backup download and equality, rejection of a stale review (409), invalid backup rejection (400) and unchanged preference values. Restore does not write scope commands or restore browser-local layout. setup-backups/ is also retained across application updates.

### Fischer Lab examples

example_catalog.py holds built-ins separately from presets.json. Notes are visible before recall; incomplete recipes are blocked in both UI and API. Saving while an example is selected requires a new personal name and does not overwrite existing personal presets.

- Sony elevator: CH1 IC503 pin 38, CH2 pin 37, DC approximately 2 V/div. CPU M3 controls through IC505, not motor terminals. Exact timebase and trigger settings were not recorded; recall remains disabled.
- Sony serial: explicit proposed CH1 pin 24 SCK input, CH2 pin 26 serial-data input; DC 2 V/div, 1 ms/div, Edge CH1 falling around 2.5 V, Auto. This is a suggested start, not a verified capture. Reference pin 2 clock output, pin 3 data output; pin 25 unused.
- Both completed recipes propose physical 10x probes and matching scope 10x settings. Prior attenuation was not recorded. Wiring and switches cannot be changed by recall. Exact signal timing/amplitudes and Sony hardware operation are not verified by this release. Establish and test a configuration, then save its readback under a new personal name.

The dashboard and Setup also link back to the instrument suite using the current hostname without port 8081. The production server and HP controller remain separate and unchanged.

### Release checks and limits

24 Python regression tests pass: run `python -m unittest -v test_scope_io test_screen_effect test_archive_tools` in the controller venv. Six Node regression scenarios pass: run `node test_refresh.js`; the sixth covers stale/failed/manual-snapshot freshness. Browser verification includes desktop/mobile layouts, local assets and anchors, screenshot enlargement and recipe notes. Physical Android touch, Sony recipe captures, an actual DHCP popup, a fresh second-Pi installation and full rollback rehearsal remain unverified. The existing user service still has Linger=no on this Pi and requires login for user-service startup.

## Trigger source indicator

A channel-colored outline and TRIGGER SOURCE badge identify all measurement entries belonging to the actual Edge trigger source. The channel control panel also receives a badge. Acquisition-status polling reads trigger source/type without refreshing control inputs. External and complex trigger sources are described rather than falsely highlighting CH1/CH2. On connection failure highlighting clears. Amber measurement warnings remain text/warning icons and do not indicate trigger source.


## v0.3.1: production startup and Ethernet discovery

Trigger-source badges and channel-colored outlines follow actual Edge trigger readback without replacing control inputs. Measurement warnings use explanatory text/icons rather than a competing outline.

Initial hostname resolution, RPC portmapper discovery and TCP connect now share the configured connection-timeout budget. This closes a python-vxi11 0.9 discovery gap: its normal operation timeout was applied only after connecting. Resolver waits and sockets are bounded locally without changing global process socket settings. A failed transport is discarded, and the scope lock is released for recovery. Two regression tests cover a TCP peer that accepts but never answers discovery, and a stalled DNS lookup.

Current regression commands:

    python -m unittest -v test_scope_io test_screen_effect test_archive_tools test_ethernet_transport
    node test_refresh.js
    node test_trigger.js

The 26 Python tests and seven Node checks cover the current source. Current live checks also exercise identity, paired images, both 10,000-sample CSV records, measurement qualifiers, control readback, preset save/recall, capture bundles and recovery from an unavailable scope.

For unattended startup, enable the supplied user service and enable lingering for its account:

    systemctl --user enable --now tektronix-controller.service
    sudo loginctl enable-linger USERNAME

The deployed live account has Linger=yes. Historical notes above describe the earlier test account's Linger=no. The HP service, HTTPS/authentication configuration and private preferences are maintained separately. HP Modern and Classic navigation use the current host and scope port 8081; scope-to-suite navigation respects the suite's existing HTTP-to-HTTPS redirect.

The scope lock coordinates processes on one host. Keep the test scope service stopped while the live controller owns the instrument, so independent hosts cannot interleave transfer settings. The apps remain separate processes; a failed scope request must not block HP requests.

Repository publication excludes connection.json, appearance.json, measurement-selection.json, presets.json, setup-backups, credentials, deployment-preferences, backups and temporary captures. Personal examples and the documentation screenshots are included only in a repository verified private.


## v0.3.2: panel sizes

Choose Customize Layout to move panels or choose Default, Half width or Full width. On desktop, adjust height with the lower-right resize grip, Shorter/Taller buttons, or Auto height to let the content determine panel height. Short fixed-height panels scroll internally so controls remain accessible. Width, height and order are saved in browser local storage. Existing saved panel order is retained. Reset Layout clears both order and size preferences. At viewport widths of 900 pixels or less, panels use one column and automatic height; desktop size preferences remain stored. Layout changes do not send instrument commands. Browser-local layout is not part of controller Setup export/restore.

Browser verification: Half/Full width, Shorter/Auto height, order and size persistence across reload, Reset Layout, and a 390-pixel single-column mobile viewport passed. Existing image-refresh and trigger-indicator regression checks passed. Layout editing leaves scope control requests available. Physical Android touch operation remains unverified.

### Shared instrument menu

After successful installation, the installer registers with the optional [Fischer Instrument Suite](https://github.com/RLF62/instrument-suite) manager. Missing or busy managers report registration as pending without failing installation. Existing integrated and legacy services are protected from removal until migrated to separate services. Registration sends no instrument commands.

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
