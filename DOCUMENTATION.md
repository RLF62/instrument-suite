# Documentation

## Current guides

| Task | Guide |
| --- | --- |
| Signed installation, updates, web authorization and rollback | [One-command maintenance](ONE_COMMAND_UPDATER.md) |
| First USB-GPIB connection and HP 6033A supply setup | [Connect an instrument](GPIB_SETUP.md) |
| Existing HTTPS installation migration | [Gateway migration](GATEWAY_MIGRATION.md) |
| Release acceptance and remaining limits | [Current validation](FRESH_CARD_VALIDATION.md) |
| Original catalog and removal workflow | [Catalog](CATALOG.md) |
| Original meter-only installer | [Standalone](STANDALONE.md) |
| Original integrated source installer | [Install](INSTALL.md) |

## Historical validation

The following records describe individual development stages. Their pending-work statements are not the current release status.

- [Initial maintenance engine checks](VALIDATION_ONE_COMMAND.md)
- [Connected updater checks](CONNECTED_UPDATER_VALIDATION.md)
- [HTTPS migration fixtures](HTTPS_MIGRATION_VALIDATION.md)
- [Production comparison before enrollment](PRODUCTION_MIGRATION_REVIEW.md)
- [Preserved supply dashboards](PRESERVED_SUPPLY_UI_VALIDATION.md)
- [Release builder](RELEASE_BUILD_VALIDATION.md)
- [Status and deployment detection](STATUS_DEPLOYMENT_VALIDATION.md)

## Repository responsibilities

The suite owns the signed manifest, coordination engine and central `approved/packages` ZIP catalog. Individual controller repositories own their application source, manuals, screenshots and component releases. ZIP catalog packages and signed release archives are separate distribution paths. Runtime state and private recovery archives do not belong in either source tree.
