"""Contract readbacks for InjectionJudge and SkillDirectory, read with gen_call.

    python3 scripts/readback.py > docs/evidence/readbacks.md
"""

import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

import genlayer_read  # noqa: E402

RPC = "https://studio-dev.genlayer.com/api"
JUDGE = "0x9619015C5Aa5e75F62436Fa8461C34f350E764d9"
DIRECTORY = "0xEE840c1CE979637F4E07868Ce61aa914212404da"


def view(contract: str, method: str, *args):
    for attempt in range(4):
        time.sleep(2.5 * attempt + 0.6)  # Studio Next rate limits gen_call
        try:
            return json.loads(genlayer_read.read_view(RPC, contract, method, list(args)))
        except genlayer_read.ReadError:
            if attempt == 3:
                raise


def main() -> int:
    stats = view(JUDGE, "get_stats")
    constants = view(JUDGE, "get_constants")
    rulings = view(JUDGE, "list_rulings", 0, 50)["items"]
    skills = view(DIRECTORY, "get_skills")["items"]
    out = [
        "# Contract readbacks",
        "",
        f"Read {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())} with `gen_call` through `{RPC}`.",
        "",
        f"## InjectionJudge `{JUDGE}` (version {constants['VERSION']})",
        "",
        f"`get_stats`: {stats['rulings']} rulings over {stats['texts']} distinct texts and {stats['urls']} URLs; "
        f"{stats['judged']} model rulings run, {stats['cached']} requests answered from storage; current verdicts "
        f"SAFE {stats['verdicts']['SAFE']}, POISONED {stats['verdicts']['POISONED']}, UNCLEAR {stats['verdicts']['UNCLEAR']}.",
        "",
        "| rid | Kind | Source | Verdict | Attempts | Final | Hard flags | Quote |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rulings:
        source = r["source"] if r["source"] == "inline" else r["source"].split("/")[2] + "/…/" + r["source"].split("/")[-2]
        quote = (r["quote"][:70] + "…") if len(r["quote"]) > 70 else r["quote"]
        out.append(f"| `{r['rid'][:12]}…` | {r['kind']} | {source} | **{r['verdict']}** | {r['attempts']} | "
                   f"{str(r['final']).lower()} | {', '.join(r['hard']) or 'none'} | {quote.replace('|', '/')} |")
    out += ["", f"## SkillDirectory `{DIRECTORY}`", "", "| URL | Listed | Ruling | Note |", "|---|---|---|---|"]
    for s in skills:
        out.append(f"| `{s['url']}` | {str(s['listed']).lower()} | `{s['rid'][:12]}…` | {s['note']} |")
    out.append("")
    out.append("The poisoned skill is absent: its list_skill transaction was refused on chain "
               "(`InjectionJudge ruled this skill POISONED`), see transactions.md.")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
