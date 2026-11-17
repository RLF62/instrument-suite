# Signed release acceptance — v1.0.1 baseline

The corrected installer completed fresh-card HTTP acceptance for the suite and all
three controllers. The final signed suite release also completed attended
enrollment and activation on an existing HTTPS deployment.

- All 230 regression tests passed, including meter forwarded HTTPS scheme
  preservation, rollback restoration and scope direct-listener auditing.
- The real-source supply package imported and rendered both dashboards with socket
  connections blocked and simulated readback.
- Fresh-card add/install checks retained unrelated process IDs and private settings.
  Dashboard, icon, manifest and shared-navigation checks passed.
- The production signing identity is pinned in the bootstrap. An independently
  verified encrypted recovery copy is retained outside the source repositories.
- Published manifests passed signature verification; every archive passed length
  and hash verification; dependency locks matched prepared permanent runtimes.
- Attended HTTPS enrollment and signed activation completed with no audit blockers
  and no recovery pending. Settings, credentials, certificates and controller
  wrappers were preserved.
- HTTPS update requests require the existing dashboard credentials. Foreign-origin
  requests were rejected. The fixed-action helper completed a verified backup.
- Repeating the installed signed update reported already up to date and retained
  all controller, broker and gateway process IDs.
- Backup verification and rollback preview passed. An actual production rollback
  and unexpected power-loss recovery were not performed.

The production HTTPS update API uses a loopback-only proxy connection with
sanitized forwarding headers; the existing Unix dashboard listener remains.
This deployment requirement is documented in [ONE_COMMAND_UPDATER.md](ONE_COMMAND_UPDATER.md).

Stable assets are immutable. A corrected suite package was published under a new
version, preserving the three controller archive bytes. Private configuration,
credentials and signing keys are excluded from public source and assets.

## v1.0.2 package verification

The corrected catalog lifecycle helper and its signed setup flow are included in
v1.0.2. Fresh bootstraps configure the helper automatically. Existing v1.0.1
updaters run `sudo instrument-suite configure-catalog` once after updating;
that command verifies the suite signature before privileged helper setup.

- 241 tests ran successfully with 21 expected unprivileged skips. The preceding
  237-test lifecycle build passed with root privileges.
- New fixtures cover fresh setup without legacy ZIP assets, unchanged controller
  and gateway services, and helper/service/sudoers recovery on setup failure.
- The published manifest signature, pinned public key, all four archive hashes
  and lengths, and downloaded-byte identity to the build passed independently.
- The three controller archives remain byte-for-byte unchanged. Only the suite
  package and signed manifest changed; manifest sequence is 3.
- The real v1.0.2 removal/reinstall test on spare hardware remains pending. This
  package verification did not remove an installed instrument or deploy v1.0.2
  over the production application.
