# Fresh-install HTTP candidate validation

The corrected development candidate completed the fresh-install acceptance checks for the suite dashboard and all three supported controllers.

- All 226 software tests passed.
- A real-source package smoke check imported the supply application, rendered both dashboards and verified the launcher/maintenance-guard contract. All socket connections were blocked and readback was simulated during this smoke check.
- Adding the supply succeeded after correcting the launcher API mismatch. Existing unrelated services retained their process IDs; existing private settings and the web-update policy retained their hashes.
- All controller dashboards, icon and manifest assets, and shared navigation passed HTTP checks.
- Repeating the same update reported already up to date and restarted no services.
- Backup verification and rollback preview passed without restarting services. No recovery remained pending.
- Trusted-LAN web backup succeeded without a separate update password. Missing CSRF, foreign-origin and unsupported-action requests were rejected.

These results cover a private development candidate and rollback preview. They do not establish a completed real rollback of this candidate or production enrollment.

Remaining release work includes the production signing identity and key backup, public bootstrap pinning, immutable public release verification, fresh HTTPS acceptance and attended enrollment of an existing HTTPS installation. The development bootstrap remains gated. Private test artifacts and test signing keys must not be published as production release assets.
