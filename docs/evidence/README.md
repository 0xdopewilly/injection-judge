# Evidence

| File | What it is | How to verify it |
|---|---|---|
| `v3-rulings.jsonl` | the v3 run (2026-10-19, live): the same 15 calls replayed on v3, one JSON line each: label, hash, status, votes, returned value. Two ended UNDETERMINED (status `UNDETERMINED`, `ok: false`): the validators did not reproduce the leader's UNCLEAR, so nothing was stored | look up each hash on the explorer |
| `v2-rulings.jsonl` | the v2 run (2026-10-19): the 15 calls of the v1 run replayed unchanged, one JSON line each: label, hash, status, votes, returned value | look up each hash on the explorer |
| `rulings.jsonl` | the v1 run (2026-10-15), same format | look up each hash on the explorer |
| `transactions.md` | all three runs plus all six deployments, decoded from `eth_getTransactionByHash`, with the SHA-256 of the code stored in each deploy transaction | `python3 scripts/tx_table.py <deploy hashes> > /tmp/t.md` and compare |
| `readbacks.md` | v3's `get_stats`, `list_rulings`, SkillDirectory's `get_skills`, and `get_ruling` for one ruling per verdict showing the stored fixed reason, read with `gen_call` | `python3 scripts/readback.py` |

The poisoned sample skill is served by the ToolBond demo server
(`https://toolbond-demo-mcp.vercel.app/skills/commit-helper-poisoned/SKILL.md`, source in
github.com/0xdopewilly/toolbond `apps/demo-mcp/api/skill.js`); it is fixed text, so anyone can
fetch it and recompute its hash.
