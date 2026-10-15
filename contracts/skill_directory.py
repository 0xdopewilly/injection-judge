# v0.3.0
# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }
"""SkillDirectory: an example consumer of InjectionJudge.

A directory of agent skills that lists a skill only when InjectionJudge's ruling for the text
validators fetched from its URL is SAFE for kind "skill". The directory never calls a model or
the web itself: it reads the ruling with a cross-contract view, so its listings rest on
InjectionJudge's validator consensus. recheck() drops a listing when a newer fetch of the same
URL is no longer SAFE.
"""

# GENERATED from contracts/src/skill_directory.py by scripts/bundle.py. Do not edit.
import json
import typing
from dataclasses import dataclass

import genlayer as gl
from genlayer.storage import allow as allow_storage

ERR_EXPECTED = "[EXPECTED]"
MAX_LIST = 50


def _fail(message: str) -> typing.NoReturn:
    raise gl.vm.UserError(ERR_EXPECTED + " " + message)


def _sender() -> str:
    address = gl.message.sender_address
    return (address.as_hex if hasattr(address, "as_hex") else str(address)).lower()


def _now() -> str:
    try:
        value = getattr(gl.message, "datetime", None)
        return str(value) if value else ""
    except Exception:
        return ""


def _is_address(text: str) -> bool:
    return len(text) == 42 and text.startswith("0x") and all(ch in "0123456789abcdef" for ch in text[2:])


def _judge_url_ruling(judge: str, url: str) -> dict:
    """InjectionJudge.get_url(url), read through a cross-contract view (the only external read)."""
    raw = gl.contract.get_at(gl.Address(judge)).view().get_url(url)
    return json.loads(str(raw))


def _dumps(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@allow_storage
@dataclass
class Entry:
    url: str
    rid: str
    text_hash: str
    purpose: str
    caps: str
    listed: bool
    listed_by: str
    updated_at: str
    note: str


class SkillDirectory(gl.contract.Contract):
    judge: str
    entries: gl.storage.TreeMap[str, Entry]
    urls: gl.storage.DynArray[str]

    def __init__(self, judge: str):
        candidate = str(judge).strip().lower()
        if not _is_address(candidate):
            _fail("judge must be the InjectionJudge contract address")
        self.judge = candidate

    @gl.public.write
    def list_skill(self, url: str) -> typing.Any:
        """List a skill whose fetched text InjectionJudge ruled SAFE as a skill."""
        url = str(url).strip()
        ruling = _judge_url_ruling(self.judge, url)
        if not ruling.get("found"):
            _fail("InjectionJudge has no ruling for this URL: call rule_url on it first")
        if ruling.get("kind") != "skill":
            _fail("the ruling is for kind " + str(ruling.get("kind")) + ", not skill")
        if ruling.get("verdict") != "SAFE":
            _fail("InjectionJudge ruled this skill " + str(ruling.get("verdict")))
        if url not in self.entries:
            self.urls.append(url)
        self.entries[url] = Entry(
            url=url, rid=str(ruling["rid"]), text_hash=str(ruling["text_hash"]), purpose=str(ruling["purpose"]),
            caps=str(ruling["caps"]), listed=True, listed_by=_sender(), updated_at=_now(), note="ruled SAFE",
        )
        return {"ok": True, "url": url, "rid": ruling["rid"], "text_hash": ruling["text_hash"]}

    @gl.public.write
    def recheck(self, url: str) -> typing.Any:
        """Anyone can ask: is the latest ruling for this URL still SAFE? If not, delist it."""
        url = str(url).strip()
        if url not in self.entries:
            _fail("this URL is not in the directory")
        entry = self.entries[url]
        ruling = _judge_url_ruling(self.judge, url)
        still_safe = bool(ruling.get("found")) and ruling.get("kind") == "skill" and ruling.get("verdict") == "SAFE"
        if still_safe:
            entry.rid, entry.text_hash = str(ruling["rid"]), str(ruling["text_hash"])
            entry.note = "ruled SAFE"
        else:
            entry.listed = False
            entry.note = "delisted: latest ruling is " + str(ruling.get("verdict") or "missing")
        entry.updated_at = _now()
        return {"ok": True, "url": url, "listed": bool(entry.listed), "note": entry.note}

    @gl.public.view
    def get_skills(self) -> str:
        items = []
        for index in range(min(len(self.urls), MAX_LIST)):
            entry = self.entries[self.urls[index]]
            items.append({
                "url": entry.url, "rid": entry.rid, "text_hash": entry.text_hash, "purpose": entry.purpose,
                "caps": entry.caps, "listed": bool(entry.listed), "note": entry.note, "updated_at": entry.updated_at,
            })
        return _dumps({"judge": self.judge, "items": items})
