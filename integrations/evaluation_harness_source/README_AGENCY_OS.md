# Evaluation engine migration source

This folder retains reusable evaluation primitives from the uploaded Harness: evaluation packs, deterministic metric calculations, scoring/quality-gate logic, experiment utilities, generic adapter contracts and reusable guardrail/lineage services.

Portfolio-specific target registry/configuration, adapters, datasets, dashboards, API entrypoints and deployment topology have been excluded from this Agency OS workspace. Evaluation datasets will be created under OS governance using synthetic fixtures first, then tenant-scoped and explicitly authorized client datasets.

The retained modules are migration inputs, not a running standalone API. They must be adapted to the Agency OS execution-event contract, tenant scope, data classification, budgets, and audit model before production use.
