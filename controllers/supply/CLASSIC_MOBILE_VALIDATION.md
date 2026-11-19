# Classic mobile width correction

> Historical isolated-browser validation. Deployment-status statements below describe that test stage. See the [current suite acceptance](https://github.com/RLF62/instrument-suite/blob/main/FRESH_CARD_VALIDATION.md) for subsequent production activation; physical Android touch behavior is a separate check.

The previous v1.0.0 Android CSS set body > main.instrument to 100% width. The layout editor now wraps that element, so its flex child wrapper shrank to intrinsic width. Existing navigation rules also gave every descendant link a full-width row and large margins.

The correction is scoped to the Classic template's max-width:700px media query. It sets the new wrapper's width and compacts the existing links. No JavaScript, control markup, preset/configuration logic, other templates or shared navigation script changed.

Isolated Chromium tests used the actual development rendered HTML and shared navigation, with network requests intercepted and all API calls blocked. Panel widths before/after: 360px viewport 198/346; 390px 198/376; 412px 198/398; 700px 198/656. Desktop 1280px remained 1120/1120. No horizontal overflow was observed. Phone navigation decreased from 430px to 86px. Desktop navigation remained 40px.

A read-only development preview serves the corrected page separately, rejects all write methods and does not proxy instrument APIs. All live controller and broker process IDs remain unchanged. Production was inspected read-only and was not deployed. Physical Android review and approval are required before production deployment.
