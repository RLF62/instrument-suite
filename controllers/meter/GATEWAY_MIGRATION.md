# HTTPS gateway and independent controller services

The shared suite can retain an existing HTTPS site while running the supply, multimeter and scope as separate services. Removing one controller leaves the suite gateway and the other instruments available.

## Service arrangement

| Service | Role |
| --- | --- |
| `fischer-suite-web` | Stable web gateway behind the existing Nginx HTTPS configuration |
| `hp6033a` | Supply backend on loopback port 8083 |
| `hp34401a` | Multimeter backend on loopback port 8082 |
| `tektronix-controller` | Independent system service using its existing Ethernet HTTP port 8081 |
| `fischer-gpib` | Shared adapter broker; controller removal does not restart it |
| `fischer-suite-manager` | Approved installation, removal, registration and recovery |

The gateway uses its own Python environment and the existing Unix socket path. It does not import instrument controllers or issue instrument commands. Each backend retains its own application directory and Python environment.

## Deployment policy

The administrator-created `/etc/fischer-suite/profile.json` enables the HTTPS arrangement:

```json
{"schema": 1, "https_gateway": true}
```

This is an example policy, not a copy of a server configuration. The file must be root-owned and must not be writable by other users. Invalid policy, or missing policy when the gateway service exists, stops activation rather than exposing a backend.

With this policy, the root activation helper binds supply and meter services only to `127.0.0.1`. The menu keeps their HTTPS URLs and uses the existing scope HTTP port. Ordinary standalone installations without this policy retain their existing behavior.

## Authentication and settings

The gateway preserves the existing control authentication mode and bcrypt credentials. Current supply authentication takes precedence while that controller is installed. A private snapshot under `instrument-suite/security` keeps authentication available after supply removal; the manager updates that snapshot after stopping the supply.

Reinstallation restores retained configuration, presets, version metadata and authentication. Choosing to reset an instrument's settings does not erase the gateway's authentication policy. The manager keeps the shared broker's Python environment if it lives inside a removed controller directory.

The existing HTTPS certificate, Nginx network restrictions and browser origins are retained. Scope connection preferences, presets, captures and browser appearance/layout preferences remain separate from controller code.

## Existing legacy installations

Installing or refreshing the catalog does **not** automatically migrate a legacy installation. Integrated or legacy services remain protected until an attended migration prepares and verifies the independent services.

A migration must:

1. Compare the current applications and service definitions; record live-only changes.
2. Back up applications, settings, authentication, service definitions, web-server configuration and manager state. Verify the archive and record rollback.
3. Prepare independent runtimes before interrupting web services.
4. Retain the shared GPIB broker and its runtime. Do not reset the adapter or send instrument-setting/output commands.
5. Preserve the existing HTTPS origin and authentication while separating the supply and meter. Disable the legacy scope user service before starting its system service.
6. Verify every menu destination and local binding, then test each controller's removal/reinstall while checking the other controllers and the gateway remain available.
7. Compare protected settings/authentication hashes and confirm the broker process was not restarted.

Production-specific migration scripts, backup manifests, credentials, certificates, captures and live settings are operational material and are **not** published here. The reusable gateway, deployment-policy support, activation helper and tests are included.

## Catalog maintenance

The current `deploy_manager.py` includes the deployment-policy helper and gateway code, restarts an already running gateway after a code refresh, and restores/restarts the previous web services if activation fails. Use this current source when maintaining a migrated installation; an older manager does not understand the gateway policy.

New instrument packages remain checksum-verified. Downloads are maintained centrally in [approved/packages](https://github.com/RLF62/instrument-suite/tree/main/approved/packages); the multimeter repository links to those copies.

## Validation

The deployed arrangement passed independent removal/reinstall tests for all three controllers. A supply removal/reinstall also passed through the public HTTPS management endpoints. Other controller application files stayed unchanged, protected settings/authentication hashes matched, and the broker process stayed running. Software regression results are recorded with the publication commit.

The publication regression passed 104 software checks, including standard standalone behavior, gateway authentication, profile handling, metadata retention and failed-gateway-deployment recovery.

## Gateway unit template

A [generic gateway service template](https://github.com/RLF62/instrument-suite/blob/main/deploy/fischer-suite-web.service.example) documents the separate runtime, Unix socket, ownership and service hardening used by this arrangement. It contains no host address, credentials or TLS key material. Prepare and validate the runtime, backend services and root-owned policy before enabling it; it is not an unattended migration installer.
