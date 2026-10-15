# Evidence

| File | What it is | How to verify it |
|---|---|---|
| `rulings.jsonl` | every write sent during the live run, one JSON line each: label, hash, status, votes, returned value | look up each hash on the explorer |
| `transactions.md` | the same transactions plus both deployments, decoded from `eth_getTransactionByHash` | `python3 scripts/tx_table.py <deploy hashes> > /tmp/t.md` and compare |
| `readbacks.md` | `get_stats`, `list_rulings` and SkillDirectory's `get_skills`, read with `gen_call` | `python3 scripts/readback.py` |

The poisoned sample skill is served by the ToolBond demo server
(`https://toolbond-demo-mcp.vercel.app/skills/commit-helper-poisoned/SKILL.md`, source in
github.com/0xdopewilly/toolbond `apps/demo-mcp/api/skill.js`); it is fixed text, so anyone can
fetch it and recompute its hash.
