# Deployment-aware status validation

The updater status command now uses the protected deployment policy to distinguish the existing HTTPS gateway from the HTTP dashboard. HTTPS reports the HTTPS root URL and fischer-suite-web journal; HTTP retains port 8080 and fischer-suite-dashboard. The address remains an explicit placeholder, not an inferred server address. An invalid deployment policy fails closed rather than advertising an HTTP fallback.

Three isolated regression tests cover HTTPS, HTTP, and policy rejection. They verify status does not activate packages or start/stop services. The complete development-Pi suite passed: 207 tests in 9.811 seconds, exit status 0. These changes are in the review checkout only; no running application, instrument setting or production service was changed.

Outstanding gates: attended enrollment for existing HTTPS installations, reviewed public artifact provenance and signing, clean-card installation acceptance, and production deployment validation. This result does not declare the public installer ready.
