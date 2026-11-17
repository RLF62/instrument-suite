# Development validation record

Status: local candidate v0.1.2 validated on a clean 64-bit Raspberry Pi OS card.
No public release was published and no production deployment was performed.

- All three selected controllers and the shared dashboard installed successfully.
- Signed local candidate updates used the shared transaction engine, detached Ed25519 verification, artifact hashes, isolated hash-locked dependencies and verified backups.
- All 180 software tests passed, including instrument safety simulations, activation failure/rollback, replay/expiry, archive validation, authentication preservation and web request authorization.
- Live trusted-LAN HTTP status and a privileged backup succeeded without a separate update password.
- Live invalid/missing origin, invalid CSRF and outside-LAN requests were rejected.
- The supply, meter, scope and GPIB broker kept their original process IDs throughout the dashboard-only updates.
- Instrument configuration hashes matched the pre-update backup.
- The existing web policy remained byte-for-byte unchanged during upgrade.
- Private transaction/backup directories were verified inaccessible to group/other users.
- All dashboards and the update helper are active, and no recovery is pending.
- HTTPS credential reuse was tested with an existing bcrypt fixture, including a password shorter than twelve characters; a physical HTTPS deployment was not performed on this HTTP test card.

Public GitHub update discovery correctly reports that no approved signed suite release is published. The public bootstrap remains gated on a reviewed signing identity and release approval. Hardware commissioning, real connected-instrument interlocks and the remaining full acceptance matrix must be completed before calling the entire updater production-ready. Local candidate keys are test-only and remain outside Git.


## Production boundary and publication

The reviewed HP Classic mobile CSS and controller icon assets were deployed to
the existing HTTPS host as UI-only changes. Settings and authentication hashes
and controller process IDs were preserved. The stable controller sources and
three checksum-verified ZIPs were published separately to main.

This maintenance candidate is published on a development branch only. Its
bootstrap remains fail-closed with an unconfigured public signing identity.
It is not enrolled on the existing production installation. Attended enrollment
and real connected-instrument interlock validation remain release blockers.
