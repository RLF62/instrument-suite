# Connected updater acceptance checks

> Historical validation record. Status and unfinished-work statements below describe this testing stage. The signed release and attended HTTPS acceptance subsequently completed; see [current acceptance](FRESH_CARD_VALIDATION.md) and [current installation/maintenance](ONE_COMMAND_UPDATER.md).


Validated on the development Raspberry Pi on 2026-11-16 (America/Chicago), using UsbGpib V2 firmware reporting V2.5. Production was inspected read-only and was not changed.

## Passed

- All 193 software regression tests passed, including isolated HTTPS authentication and filesystem migration fixtures.
- Live supply maintenance lease verified output OFF and remote programming disabled.
- Live meter maintenance lease verified polling paused and no queued operations.
- Live scope maintenance lease rejected running/busy acquisition; after the operator stopped acquisition it verified stopped and not busy.
- A private signed local meter-only candidate completed staging, integrity checks, backup, activation and health checks. Its only deliberate content change was a README acceptance marker; existing live branding assets were preserved.
- Repeating that candidate returned already up to date with no services restarted.
- Explicit CLI rollback restored the meter's original managed code and passed health checks.
- A test-only injected activation failure, raised after the real activation health checks, exercised the transaction engine's automatic restore and recovery health checks. No safety checks were overridden, and the failure injection was confined to the test process.
- Final hashes matched the baseline for all managed component code and five private configuration/settings files. Supply, scope, shared dashboard and broker process IDs were unchanged throughout the meter update and recovery tests. No pending recovery or maintenance gate remained; supply output stayed OFF and remote programming disabled.

## Limits and remaining release gates

These were local candidates signed with the existing private development key. They are not public releases and do not establish a production signing identity. The meter candidate was rolled back; its synthetic version and documentation marker must not be published as a controller release.

The running development files include branding changes newer than the original candidate package metadata. Public artifacts must be rebuilt from reviewed repository commits with accurate version/provenance records; do not reuse historical candidate commit labels for new content.

Existing production uses a protected HTTPS gateway and controller services without updater maintenance wrappers. It requires an attended migration, private backup, configuration comparison and permanent runtime preparation. At inspection no USB-GPIB adapter was attached to production, so connected safety verification and production activation were blocked.

Still required before a stable release: attended existing-HTTPS enrollment validation; remaining fresh-install/component-selection/add-remove acceptance matrix; final immutable artifact build and signature verification; administrator-controlled release-key backup and pinning; and production comparison, backup and live safety checks. Do not remove bootstrap gates or legacy removal protections to bypass these requirements.
