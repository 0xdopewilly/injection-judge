# Evidence

| File | What it is | How to verify it |
|---|---|---|
| `v2-rulings.jsonl` | the v2 run (2026-10-19): the 15 calls of the v1 run replayed unchanged, one JSON line each: label, hash, status, votes, returned value | look up each hash on the explorer |
| `rulings.jsonl` | the v1 run (2026-10-15), same format | look up each hash on the explorer |
| `transactions.md` | both runs plus all four deployments, decoded from `eth_getTransactionByHash`, with the SHA-256 of the code stored in each deploy transaction | `python3 scripts/tx_table.py <deploy hashes> > /tmp/t.md` and compare |
| `readbacks.md` | v2's `get_stats`, `list_rulings` and SkillDirectory's `get_skills`, read with `gen_call` | `python3 scripts/readback.py` |

The poisoned sample skill is served by the ToolBond demo server
(`https://toolbond-demo-mcp.vercel.app/skills/commit-helper-poisoned/SKILL.md`, source in
github.com/0xdopewilly/toolbond `apps/demo-mcp/api/skill.js`); it is fixed text, so anyone can
fetch it and recompute its hash.
