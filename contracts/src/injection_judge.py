# v0.3.0
# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }
"""InjectionJudge: consensus rulings on whether text an AI agent will follow is poisoned.

Agents now load instructions from many places they do not control: MCP tool descriptions,
skill files, rules files such as AGENTS.md, shared system prompts. One injected sentence there
can make an agent leak files or hide what it does. InjectionJudge gives any contract or client
a ruling it can rely on: SAFE, POISONED or UNCLEAR for a given text, kind, declared purpose and
declared capabilities, decided by GenLayer validators.

Consensus design, one line per decision:
- screening: red flags are computed in code (lib/redflags.py, lib/verdict.py), identical on
  every validator; a hard flag makes SAFE impossible whatever a model says;
- judging: each validator runs two differently worded readings that must agree; validators
  must reproduce the leader's verdict word exactly, UNCLEAR included, so no verdict is taken on
  the leader's word; SAFE and UNCLEAR carry no quote; POISONED must quote text that code
  finds in the (revealed) text;
- fetching (rule_url): every validator fetches the URL itself and must derive the identical
  text, so what is judged and stored is what all of them saw.

Rulings are content-addressed: rid = sha256 of {text_hash, kind, purpose, caps}. A text ruled
SAFE or POISONED keeps that ruling; an UNCLEAR one can be retried until it has been judged
MAX_ATTEMPTS times. Other contracts read rulings with verdict_of / lookup. The interface is
documented in docs/CONTRACT_API.md.
"""

import hashlib
import json
import typing
from dataclasses import dataclass

import genlayer as gl
from genlayer.storage import allow as allow_storage

# @@include redflags
# @@include verdict

ERR_EXPECTED = "[EXPECTED]"
ERR_EXTERNAL = "[EXTERNAL]"
ERR_TRANSIENT = "[TRANSIENT]"

CONTRACT_VERSION = "1"
MAX_TEXT_BYTES = 12000
MAX_PURPOSE_CHARS = 280
MAX_URL_CHARS = 300
MAX_ATTEMPTS = 3
MAX_LIST = 50
ALLOWED_CAPS = ("none", "network", "filesystem", "credentials", "shell", "payments")
HOST_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789.-"
PRIVATE_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home", ".arpa")
ACCEPT = "text/plain, text/markdown, application/json;q=0.9, */*;q=0.1"


# ---------------------------------------------------------------------------- helpers


def _fail(message: str) -> typing.NoReturn:
    raise gl.vm.UserError(ERR_EXPECTED + " " + message)


def _hex(address: typing.Any) -> str:
    return (address.as_hex if hasattr(address, "as_hex") else str(address)).lower()


def _sender() -> str:
    return _hex(gl.message.sender_address)


def _now() -> str:
    """The transaction's own ISO datetime, identical on every validator ("" if absent)."""
    try:
        value = getattr(gl.message, "datetime", None)
        return str(value) if value else ""
    except Exception:
        return ""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _dumps(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _normalize_kind(kind: str) -> str:
    return str(kind).strip().lower()


def _normalize_caps(caps: str) -> str:
    """Sorted, de-duplicated capability list, or "" when it contains an unknown capability."""
    items = sorted({part.strip().lower() for part in str(caps).split(",") if part.strip()})
    if not items or any(item not in ALLOWED_CAPS for item in items):
        return ""
    if "none" in items and len(items) > 1:
        return ""
    return ",".join(items)


def _ruling_id(text_hash: str, kind: str, purpose: str, caps: str) -> str:
    """The content address of a ruling: what was judged, as what, against which declaration."""
    return _sha256(_dumps({"caps": caps, "kind": kind, "purpose": purpose, "text_hash": text_hash}))[:32]


def _host(url: str) -> str:
    rest = url[len("https://"):]
    end = len(rest)
    for separator in "/?#\\":
        index = rest.find(separator)
        if 0 <= index < end:
            end = index
    return rest[:end].lower()


def _url_problem(url: str) -> str:
    if len(url) > MAX_URL_CHARS:
        return "url is longer than " + str(MAX_URL_CHARS) + " characters"
    if not url.startswith("https://"):
        return "url must start with https://"
    if any(ch.isspace() for ch in url) or "\\" in url:
        return "url must not contain whitespace or backslashes"
    host = _host(url)
    if not host or any(ch not in HOST_CHARS for ch in host):
        return "url host must be a domain name without port, credentials or other symbols"
    labels = host.split(".")
    if len(labels) < 2 or not all(labels) or not labels[-1].isalpha():
        return "url host must be a public domain name"
    if host == "localhost" or host.endswith(PRIVATE_SUFFIXES):
        return "url host must be a public domain name"
    return ""


def _text_problem(text: str) -> str:
    if not text.strip():
        return "text is empty"
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        return "text is larger than " + str(MAX_TEXT_BYTES) + " bytes"
    if "\x00" in text:
        return "text contains NUL bytes"
    return ""


def _error_text(err: typing.Any) -> str:
    for attr in ("data", "message"):
        value = getattr(err, attr, None)
        if isinstance(value, str) and value:
            return value
    return str(err)


def _same_failure(leaders_res: typing.Any, leader_fn: typing.Callable) -> bool:
    leader_msg = _error_text(leaders_res)
    try:
        leader_fn()
    except gl.vm.UserError as err:
        mine = _error_text(err)
        if mine.startswith(ERR_TRANSIENT) and leader_msg.startswith(ERR_TRANSIENT):
            return True
        return mine == leader_msg
    except Exception:
        return False
    return False


# --------------------------------------------------------------- non-deterministic blocks


def _fetch_text(url: str) -> dict:
    """GET the URL and return its text (call only inside a nondet block)."""
    try:
        response = gl.nondet.web.get(url, headers={"Accept": ACCEPT})
    except Exception as exc:
        # validators agree on any [TRANSIENT] failure, so the detail is free to vary
        raise gl.vm.UserError(ERR_TRANSIENT + " transport failure: " + type(exc).__name__)
    if response.status != 200:
        raise gl.vm.UserError(ERR_EXTERNAL + " http " + str(response.status))
    body = response.body or b""
    if len(body) > MAX_TEXT_BYTES:
        raise gl.vm.UserError(ERR_EXTERNAL + " text larger than " + str(MAX_TEXT_BYTES) + " bytes")
    try:
        text = body.decode("utf-8")
    except Exception:
        raise gl.vm.UserError(ERR_EXTERNAL + " body is not UTF-8 text")
    problem = _text_problem(text)
    if problem:
        raise gl.vm.UserError(ERR_EXTERNAL + " " + problem)
    return {"text": text, "text_hash": _sha256(text)}


def _ask_json(prompt: str):
    """One model call in JSON mode; any failure reads as UNCLEAR downstream."""
    try:
        return gl.nondet.exec_prompt(prompt, response_format="json")
    except Exception:
        return None


# ---------------------------------------------------------------------------- storage


@allow_storage
@dataclass
class Ruling:
    rid: str
    text_hash: str
    kind: str
    purpose: str
    caps: str
    text: str  # as submitted or fetched (hidden characters included; views reveal them)
    source: str  # "inline", or the URL validators fetched it from first
    flags_json: str  # every red flag code
    hard_json: str  # the codes that block SAFE for this kind
    verdict: str
    quote: str
    reason: str
    attempts: gl.u64  # model rulings so far (UNCLEAR can be retried until MAX_ATTEMPTS)
    requested_by: str
    first_ruled_at: str
    ruled_at: str


class InjectionJudge(gl.contract.Contract):
    rulings: gl.storage.TreeMap[str, Ruling]
    ruling_ids: gl.storage.DynArray[str]
    by_text: gl.storage.TreeMap[str, str]  # text_hash -> JSON list of rids
    by_url: gl.storage.TreeMap[str, str]  # url -> rid of its latest fetch
    verdict_counts: gl.storage.TreeMap[str, gl.u64]  # current verdict of each ruling
    judged_total: gl.u64  # model rulings run, retries included
    cached_total: gl.u64  # requests answered from an existing ruling

    def __init__(self):
        self.judged_total = 0
        self.cached_total = 0

    # ------------------------------------------------------------------------- writes

    @gl.public.write
    def rule(self, text: str, kind: str, purpose: str, caps: str) -> typing.Any:
        """Rule on text submitted in the transaction."""
        text = str(text)
        problem = _text_problem(text)
        if problem:
            _fail(problem)
        kind, purpose, caps = self._declaration(kind, purpose, caps)
        return self._rule(text, kind, purpose, caps, "inline")

    @gl.public.write
    def rule_url(self, url: str, kind: str, purpose: str, caps: str) -> typing.Any:
        """Every validator fetches the URL and must see the identical text; then rule on it."""
        url = str(url).strip()
        problem = _url_problem(url)
        if problem:
            _fail(problem)
        kind, purpose, caps = self._declaration(kind, purpose, caps)

        def leader_fn() -> dict:
            return _fetch_text(url)

        def validator_fn(leaders_res: typing.Any) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                return _same_failure(leaders_res, leader_fn)
            try:
                return leader_fn() == leaders_res.calldata
            except gl.vm.UserError:
                return False

        fetched = gl.vm.run_nondet(leader_fn, validator_fn)
        text = str(fetched["text"])
        if _sha256(text) != fetched["text_hash"] or _text_problem(text):
            _fail("fetched text failed its own checks")
        result = self._rule(text, kind, purpose, caps, url)
        self.by_url[url] = result["rid"]
        result["url"] = url
        return result

    # -------------------------------------------------------------------------- views

    @gl.public.view
    def verdict_of(self, rid: str) -> str:
        """For other contracts: "SAFE", "POISONED", "UNCLEAR", or "" for an unknown ruling."""
        rid = str(rid).strip()
        return str(self.rulings[rid].verdict) if rid in self.rulings else ""

    @gl.public.view
    def ruling_id(self, text_hash: str, kind: str, purpose: str, caps: str) -> str:
        return _ruling_id(str(text_hash).strip().lower(), _normalize_kind(kind), str(purpose).strip(), _normalize_caps(caps))

    @gl.public.view
    def lookup(self, text_hash: str, kind: str, purpose: str, caps: str) -> str:
        rid = self.ruling_id(text_hash, kind, purpose, caps)
        if rid not in self.rulings:
            return _dumps({"found": False, "rid": rid})
        return _dumps(self._full(rid))

    @gl.public.view
    def get_ruling(self, rid: str) -> str:
        rid = str(rid).strip()
        if rid not in self.rulings:
            return _dumps({"found": False, "rid": rid})
        return _dumps(self._full(rid))

    @gl.public.view
    def rulings_for_text(self, text_hash: str) -> str:
        key = str(text_hash).strip().lower()
        rids = json.loads(self.by_text[key]) if key in self.by_text else []
        return _dumps({"text_hash": key, "items": [self._summary(self.rulings[rid]) for rid in rids]})

    @gl.public.view
    def get_url(self, url: str) -> str:
        key = str(url).strip()
        if key not in self.by_url:
            return _dumps({"found": False, "url": key})
        return _dumps(dict(self._full(self.by_url[key]), url=key))

    @gl.public.view
    def list_rulings(self, offset: int, limit: int) -> str:
        start = max(0, int(offset))
        count = max(0, min(int(limit), MAX_LIST))
        total = len(self.ruling_ids)
        items = [self._summary(self.rulings[self.ruling_ids[i]]) for i in range(start, min(start + count, total))]
        return _dumps({"total": total, "offset": start, "items": items})

    @gl.public.view
    def get_stats(self) -> str:
        counts = {verdict: int(self.verdict_counts[verdict]) if verdict in self.verdict_counts else 0 for verdict in VERDICTS}
        return _dumps({
            "rulings": len(self.ruling_ids), "texts": len(self.by_text), "urls": len(self.by_url),
            "judged": int(self.judged_total), "cached": int(self.cached_total), "verdicts": counts,
        })

    @gl.public.view
    def get_constants(self) -> str:
        return _dumps({
            "VERSION": CONTRACT_VERSION, "MAX_TEXT_BYTES": MAX_TEXT_BYTES, "MAX_PURPOSE_CHARS": MAX_PURPOSE_CHARS,
            "MAX_URL_CHARS": MAX_URL_CHARS, "MAX_ATTEMPTS": MAX_ATTEMPTS, "KINDS": sorted(KINDS),
            "CAPS": list(ALLOWED_CAPS), "HARD_FLAGS": {kind: list(hard_flags_for(kind)) for kind in sorted(KINDS)},
        })

    # ------------------------------------------------------------------------ private

    def _declaration(self, kind: str, purpose: str, caps: str) -> tuple:
        kind = _normalize_kind(kind)
        if kind not in KINDS:
            _fail("kind must be one of " + ", ".join(sorted(KINDS)))
        purpose = str(purpose).strip()
        if not 0 < len(purpose) <= MAX_PURPOSE_CHARS:
            _fail("purpose must be 1 to " + str(MAX_PURPOSE_CHARS) + " characters")
        if screen(purpose, "other")["hard"]:
            # the purpose reaches the judge prompt: it gets the same hard checks as the text
            _fail("purpose contains hidden characters or text aimed at the judge")
        caps_norm = _normalize_caps(caps)
        if not caps_norm:
            _fail("caps must be a comma-separated subset of " + ",".join(ALLOWED_CAPS))
        return kind, purpose, caps_norm

    def _rule(self, text: str, kind: str, purpose: str, caps: str, source: str) -> dict:
        text_hash = _sha256(text)
        rid = _ruling_id(text_hash, kind, purpose, caps)
        existing = self.rulings[rid] if rid in self.rulings else None
        if existing is not None and (existing.verdict != UNCLEAR or int(existing.attempts) >= MAX_ATTEMPTS):
            self.cached_total = int(self.cached_total) + 1
            return dict(self._summary(existing), cached=True)
        screened = screen(text, kind)
        result = self._judge(kind, purpose, caps, reveal(text), screened["flags"], screened["hard"])
        now = _now()
        verdict = str(result["verdict"])
        if existing is None:
            self.rulings[rid] = Ruling(
                rid=rid, text_hash=text_hash, kind=kind, purpose=purpose, caps=caps, text=text, source=source,
                flags_json=_dumps(screened["flags"]), hard_json=_dumps(screened["hard"]), verdict=verdict,
                quote=str(result["quote"])[:MAX_QUOTE_CHARS], reason=str(result["reason"])[:MAX_REASON_CHARS],
                attempts=1, requested_by=_sender(), first_ruled_at=now, ruled_at=now,
            )
            self.ruling_ids.append(rid)
            rids = json.loads(self.by_text[text_hash]) if text_hash in self.by_text else []
            self.by_text[text_hash] = _dumps(rids + [rid])
        else:
            self._count(existing.verdict, -1)
            existing.verdict = verdict
            existing.quote = str(result["quote"])[:MAX_QUOTE_CHARS]
            existing.reason = str(result["reason"])[:MAX_REASON_CHARS]
            existing.attempts = int(existing.attempts) + 1
            existing.ruled_at = now
        self._count(verdict, 1)
        self.judged_total = int(self.judged_total) + 1
        return dict(self._summary(self.rulings[rid]), cached=False)

    def _judge(self, kind: str, purpose: str, caps: str, revealed: str, flags: list, hard: list) -> dict:
        """Two readings per validator, which must reproduce the leader's verdict word exactly.
        UNCLEAR is not a safe harbour: it controls retries and what other contracts may rely on,
        so a validator accepts it only when its own readings also end in UNCLEAR."""

        def leader_fn() -> dict:
            return judge(lambda prompt: _ask_json(prompt), kind, purpose, caps, revealed, flags, hard)

        def validator_fn(leaders_res: typing.Any) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                return False
            theirs = leaders_res.calldata
            if not claim_valid(theirs, revealed):
                return False
            if hard and theirs["verdict"] == SAFE:
                return False
            return leader_fn()["verdict"] == theirs["verdict"]

        return gl.vm.run_nondet(leader_fn, validator_fn)

    def _count(self, verdict: str, delta: int) -> None:
        current = int(self.verdict_counts[verdict]) if verdict in self.verdict_counts else 0
        self.verdict_counts[verdict] = max(0, current + delta)

    def _summary(self, ruling: Ruling) -> dict:
        return {
            "rid": ruling.rid, "text_hash": ruling.text_hash, "kind": ruling.kind, "purpose": ruling.purpose,
            "caps": ruling.caps, "source": ruling.source, "verdict": ruling.verdict, "quote": ruling.quote,
            "flags": json.loads(ruling.flags_json), "hard": json.loads(ruling.hard_json),
            "attempts": int(ruling.attempts), "final": ruling.verdict != UNCLEAR or int(ruling.attempts) >= MAX_ATTEMPTS,
            "ruled_at": ruling.ruled_at,
        }

    def _full(self, rid: str) -> dict:
        ruling = self.rulings[rid]
        return dict(
            self._summary(ruling), found=True, reason=ruling.reason, requested_by=ruling.requested_by,
            first_ruled_at=ruling.first_ruled_at, text=reveal(ruling.text), size=len(ruling.text.encode("utf-8")),
        )
