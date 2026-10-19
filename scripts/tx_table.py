"""Decode every logged transaction from the chain into a Markdown table.

Takes hashes from docs/evidence/*.jsonl (and the deploy hashes given on the command line), fetches
each with eth_getTransactionByHash, and prints sender, contract, method, short arguments, status,
execution result, votes and the returned value or error, all decoded from the chain itself.

    python3 scripts/tx_table.py 0xdeploy1 0xdeploy2 > docs/evidence/transactions.md
"""

import base64
import hashlib
import json
import pathlib
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from genlayer_read import decode  # noqa: E402

RPC = "https://studio-dev.genlayer.com/api"
EXPLORER = "https://explorer-studio-dev.genlayer.com"
NAMES = {
    "0x2ff8e797dbcb373d463b1e3fad1d7a72496c4660": "InjectionJudge v3",
    "0xf8e75dbeafce2b460843b25ff67ccf157e0e82ac": "SkillDirectory v3",
    "0x4d938096e549fc900db9af72ac0d0af168e5d482": "InjectionJudge v2",
    "0x71c0006df02839b2030a780151bda2727045f6da": "SkillDirectory v2",
    "0x9619015c5aa5e75f62436fa8461c34f350e764d9": "InjectionJudge v1",
    "0xee840c1ce979637f4e07868ce61aa914212404da": "SkillDirectory v1",
}


def rpc(method: str, params: list):
    request = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": "injection-judge-evidence"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())["result"]


def framed(b64: str):
    raw = base64.b64decode(b64 or "")
    if not raw:
        return None, None
    if raw[0] == 0:
        try:
            value = decode(raw[1:])
            return (json.loads(value) if isinstance(value, str) and value[:1] in "{[" else value), None
        except Exception:
            return None, None
    return None, raw[1:].decode("utf-8", "replace")


def short(value, limit=80) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    text = text.replace("|", "/").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def main() -> int:
    hashes = list(sys.argv[1:])
    for path in sorted((ROOT / "docs/evidence").glob("*.jsonl")):
        for line in path.read_text().splitlines():
            h = json.loads(line).get("hash")
            if h and h not in hashes:
                hashes.append(h)
    rows = []
    for h in hashes:
        tx = rpc("eth_getTransactionByHash", [h])
        time.sleep(0.3)
        data = tx.get("consensus_data") or {}
        leader = data.get("leader_receipt")
        leader = leader[0] if isinstance(leader, list) and leader else (leader or {})
        returned, error = framed(leader.get("result", ""))
        calldata = tx.get("data", {}).get("calldata") if isinstance(tx.get("data"), dict) else None
        message = decode(base64.b64decode(calldata)) if calldata else {}
        method = message.get("", "(deploy)") if isinstance(message, dict) else "(deploy)"
        to = str(tx.get("to_address") or "").lower()
        contract = NAMES.get(to, "deploy" if method == "(deploy)" else to[:10])
        args = message.get("args", []) if isinstance(message, dict) else []
        code = tx.get("data", {}).get("contract_code") if isinstance(tx.get("data"), dict) else None
        if method == "(deploy)" and code:
            args = ["source SHA-256 " + hashlib.sha256(base64.b64decode(code)).hexdigest()]
        outcome = ""
        if isinstance(returned, dict):
            if "verdict" in returned:
                outcome = returned["verdict"] + (" (cached)" if returned.get("cached") else "") + (f", attempt {returned.get('attempts')}" if returned.get("attempts", 1) > 1 else "")
            elif "rid" in returned:
                outcome = "listed"
        if error:
            outcome = short(error, 80)
        decision = ((tx.get("consensus_history") or {}).get("latestDecision") or {}).get("status")
        if decision == "UNDETERMINED":
            # no majority reproduced the leader's result: nothing was stored
            outcome = "UNDETERMINED (" + str(tx.get("result_name")) + "): leader said " + (outcome or "nothing") + ", not stored"
        votes = list((data.get("votes") or {}).values())
        rows.append((str(tx.get("created_at", ""))[:19].replace("T", " "), contract, method, ", ".join(short(a) for a in args), tx.get("status"),
                     tx.get("txExecutionResultName"), outcome, f"{votes.count('agree')} agree, {votes.count('disagree')} disagree", h))
    print("| Created (UTC) | Contract | Call | Arguments | Status | Outcome | Votes | Transaction |")
    print("|---|---|---|---|---|---|---|---|")
    for t, contract, method, args, status, execution, outcome, votes, h in rows:
        status_text = status + ("" if execution == "FINISHED_WITH_RETURN" else ", " + str(execution))
        print(f"| {t} | {contract} | `{method}` | {args} | {status_text} | {outcome} | {votes} | [{h[:10]}…]({EXPLORER}/tx/{h}) |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
