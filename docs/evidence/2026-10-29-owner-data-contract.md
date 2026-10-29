# Owner data kept across runs and versions — contract from the CEO plan to the runner (2026-10-29)

## Automatically connected (dev source 2f4cdc5; candidate 0.1.63-2f4cdc5)
1. **Plan:** `runtime.data` in the plan schema.
   - The CEO decides whether the Owner enters data that must persist. It declares the formats (.json/.csv/.txt/
     .sqlite), `schema_version`, `compatible_from`, and one write and one read request carrying `{marker}`.
   - `runtime.normalize_data` forces `./data/`, never widens formats, and marks unverifiable declarations invalid.
     An older plan without it = not declared.
2. **Production:** the producer receives the normalized contract (`runtime_acceptance`) and the execution rules:
   - `./data/` only, atomic writes;
   - the first run works with no data; existing data is reloaded at start;
   - write/read implemented as declared; save errors are shown.
3. **Verification (executed, isolated):**
   - a fresh run writes a unique marker and reads it back;
   - `./data/` is saved with the runner's own `userdata` code;
   - it is restored into a fresh copy, restarted and read again.
   - A declaration alone or data outside `./data/` fails.
   - A strategy review cannot drop or change the contract.
4. **Runner (Owner use):**
   - saves and restores only with a declared contract, using the declared formats;
   - records the data schema with each snapshot;
   - refuses data outside `[compatible_from, schema_version]` without starting the new version, and offers
     "previous version with the data" or "new version with empty data";
   - when the previous version runs, it keeps that version's data schema;
   - grants stay limited to the run folder, as before.

## Checked
- No-model automatic tests (`tests/test_data_contract.py`):
  - normalization;
  - round trip pass, data outside `./data/` fails, unverifiable declaration fails;
  - scripted CEO plan → producer context → isolated verification round trip → runner save/restore.
- `tests/test_owner_data.py` (11): contract, live SQLite, failed save, damaged snapshot, pruning, flow, abnormal end,
  declared incompatibility, undeclared plan never restored, project separation, port retry.
- Full regression 565/565 on 2f4cdc5.
- Packaged candidate 0.1.63-2f4cdc5, web page: 18/18 with the FIXED developer test app
  (`outputs/owner-data-e2e-2f4cdc5.json`, no model call).

## Not yet checked
- That the real CEO/producer models write this contract and implement it in a generated app. No real-model run was
  started, per the instruction.
- Owner confirmation; the current server (0.1.63-50aabe2) does not have this feature.
