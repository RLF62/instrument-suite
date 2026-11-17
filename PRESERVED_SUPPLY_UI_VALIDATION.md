# Preserved HP supply UI: reviewed development work

The owner explicitly approved inspection of the two production HP supply HTML
templates. Inspection identified the shared presentation layout editor, saved
layout migration, live voltage/current/power chart, chart visibility preferences,
branding and Classic mobile width corrections. Replacing these with older
controller templates would discard working features.

The original bytes were copied to an isolated review directory on the development
Pi and their SHA-256 values matched production:

- `index.html`: `f34ee7b95c055328414db149b5561ff4dfa3fb997387b91a3883c1197c36a2f1`
- `classic_dual_preview.html`: `746538c8e1a9f414b47a0e196216a3f03adcbcec97bd2735c9cd9da32a167000`

Both templates rendered successfully in an isolated Flask/Jinja application on
the development Pi, with fixture credentials/settings and no controller modules
imported. An offline Chromium check then exercised Classic and Modern at 360,
390, 412, 700 and 1280 CSS pixels. All ten checks passed without JavaScript errors
or horizontal overflow. On a 390-pixel viewport the Classic panel measured 376
pixels, filling the body content width. Chart controls, saved visibility, layout
editing, favicon links, Apple icon and manifest metadata were present. Layout
and chart presentation actions generated zero write requests. Every browser
network request was fulfilled locally or blocked; no instrument connection was
used for these browser checks.

## Packaging correction validated on the development Pi

The reviewed templates are staged in `integration/templates/`, the same source
location used by the existing suite installer. The candidate builder now copies
both into the supply payload after applying the shared-adapter transformation,
instead of allowing older ZIP templates to replace them. The overlay leaves
controller Python code, settings and other template files untouched. Missing or
symlinked reviewed templates block packaging.

Four new regression checks cover byte-for-byte preservation, retaining unrelated
files, rejecting missing templates before either is replaced, and rejecting
symlinked source templates. The complete Linux regression suite passed on the
development Pi: 204 tests in 12.754 seconds, exit status 0. The run used the suite
virtual environment with sudo from the isolated review checkout; it did not
activate controller packages or change running services.

Production application files, settings, instrument states and services were not
changed. The existing verified private production recovery archive remains on
the production server. Public release signing, clean-card acceptance and attended
existing-HTTPS enrollment are still outstanding.
