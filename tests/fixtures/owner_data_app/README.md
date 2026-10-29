# Fixed test app for Owner data save/restore (developer fixture, NOT AI-produced)

Base: the model-generated `inventory_app.py` of packaged run P-20261029-99cea3 (candidate 0.1.63-50aabe2; v2, Codex
verification PASS), sha256 `e232bf84830402067fb8f73270fb878006842e9d8992bb8588c7edd68c6a2a5c`. The model is NOT re-run for these fixtures.

Developer changes (minimal, labelled `developer fixture addition` in the code):
- v1: a quantity form (POST /update) that saves `./data/inventory.json`; the page shows saved data when present.
- v2: v1 with a changed title, a fixed "revised code version" (compatible data).
- v3: requires a different data format (schema 3) and fails on v1 data, a fixed "incompatible revision".

`make_fixture.py` (session scratchpad) produced these files from the base. They are test material only.
