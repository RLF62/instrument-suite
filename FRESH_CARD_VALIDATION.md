# Fresh-card HTTP candidate validation

On the clean .178 Raspberry Pi Zero 2 W (64-bit Raspberry Pi OS/Debian 13, 16 GB card), the signed private candidate installed the suite and meter successfully, including OS dependencies, hash-locked wheels, systemd, Nginx and the restricted web helper.

The explicit trusted-LAN HTTP option requested no separate update password. Both local requests and real LAN requests from .108 obtained update status without authentication. Missing-CSRF and foreign-origin requests were rejected with HTTP 403. Navigation initially contained only the installed meter.

Adding Tektronix succeeded without changing the meter, broker or dashboard PIDs. The owner entered the scope connection during testing. A temporary diagnostic hold and placeholder were restored to the owner's exact settings without restarting the scope or sending control commands; the address was not inserted by the installer. The two-controller configuration and settings-preservation checks passed.

Adding the supply exposed a genuine packaging defect: the standalone supply repository lacks the supply_standalone launcher required by suite services. The worker could not import it. Automatic recovery restored the previous two-controller installation and health checks passed, with no recovery pending, no unrelated PID changes and unchanged private settings. The three-controller test did not pass on that first candidate.

The correction stages a reviewed HTTP launcher under suite integration, reusing the existing tested wrapper's origin protection and HTTP behavior while exposing the concrete supply controller expected by the maintenance entry protocol. Both package builders now include it. Activation continues to preserve existing HTTPS/authentication wrappers. A build-only wrapper source change is classified as updater/dashboard work so existing controllers and the broker do not restart solely for that asset.

Six new tests cover wrapper inclusion, missing/symlink rejection, importing the actual wrapper with an inert Flask/controller fixture, output/remote interlocks, foreign-origin rejection and restart isolation. All 223 tests passed on .108 in 18.187 seconds. Fresh-card retesting of the corrected candidate remains pending at this checkpoint.

This is development-candidate acceptance, not a public bootstrap release. The manifest and artifacts travel over a pinned local HTTPS fixture with an explicitly pinned temporary test release key and known manifest digest. The normal signature, hash, staging, backup, health, interlock and rollback code runs unchanged. GitHub stable-release discovery, public bootstrap key enrollment, fresh HTTPS acceptance, production signing and existing-HTTPS migration remain separate unfinished gates. No private keys, server configuration, credentials or private test artifacts are included in this document. Production .177 was not changed.
