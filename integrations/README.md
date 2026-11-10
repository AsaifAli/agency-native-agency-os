# Integration source snapshots

These are cleaned migration inputs from the two uploaded repositories. They are intentionally isolated from `app/` until their contracts and security behavior are ported. Do not run them as independent production services or introduce their own identity/persistence as competing sources of truth.

- `command_center_source/`: source backend modules, tests and relevant documentation.
- `evaluation_harness_source/`: reusable harness code, evaluation packs, selected tests and n8n workflow templates.

Source-level tests should be run with each source's pinned dependencies during migration. OS integration tests belong in the top-level `tests/` suite.
