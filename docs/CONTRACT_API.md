# InjectionJudge interface

Contract: [`contracts/src/injection_judge.py`](../contracts/src/injection_judge.py), bundled into
`contracts/injection_judge.py`. Live on GenLayer Studio Next (chain 61997, RPC
`https://studio-dev.genlayer.com/api`) at `0x9619015C5Aa5e75F62436Fa8461C34f350E764d9`.

## Inputs

| Field | Rule |
|---|---|
| `text` | non-empty, at most 12,000 UTF-8 bytes, no NUL bytes. Stored as given; views reveal hidden characters (`[[HIDDEN: …]]`, `⟦U+200B⟧`). |
| `url` | `https://` on a public domain name: no IP literals, ports, credentials, `localhost` or private suffixes; at most 300 characters. The response must be HTTP 200 and valid UTF-8 text within the size limit. |
| `kind` | `mcp-tool`, `skill`, `agent-rules`, `system-prompt` or `other` (case-insensitive). For `mcp-tool`, a JSON tool object gets per-field flags; anything else is flagged S2. |
| `purpose` | 1 to 280 characters. It reaches the judge prompt, so a purpose with a hard flag (hidden characters, text aimed at the judge) is refused. |
| `caps` | comma-separated subset of `none, network, filesystem, credentials, shell, payments`; normalised (sorted, lower case); `none` stands alone. |

Bad inputs raise `[EXPECTED] …` and change nothing.

## Rulings

`rid = sha256(json({"caps", "kind", "purpose", "text_hash"}, sorted keys, compact))[:32]`, where
`text_hash = sha256(utf8(text))`. The same text with a different kind, purpose or capabilities is a
different ruling; the same text submitted inline or fetched from any URL is the same ruling.

| Verdict | Meaning | Final |
|---|---|---|
| `SAFE` | both readings agree the text asks for nothing beyond its declared purpose, and no hard flag is present | yes |
| `POISONED` | both readings agree, and the quoted sentence is found in the text by code | yes |
| `UNCLEAR` | the readings disagree, the evidence did not check out, a hard flag blocked SAFE, or the model failed | after 3 attempts |

A request for a final ruling returns it from storage (`cached: true`) without running a model.

## Writes

| Method | Returns |
|---|---|
| `rule(text: str, kind: str, purpose: str, caps: str) -> dict` | `{"rid", "text_hash", "kind", "purpose", "caps", "source": "inline", "verdict", "quote", "flags", "hard", "attempts", "final", "ruled_at", "cached"}` |
| `rule_url(url: str, kind: str, purpose: str, caps: str) -> dict` | the same, plus `"url"`; `source` is the first URL the text was fetched from |

Consensus:

- Fetch block (`rule_url`): every validator runs the same GET and must return the identical
  `{"text", "text_hash"}`. If the leader failed, validators accept only the same classified
  error (`[EXTERNAL] http 404`, `… not UTF-8 text`, `… larger than …`); `[TRANSIENT]` failures
  match each other.
- Judge block: the leader's ruling must have the right shape and sizes, and a POISONED quote that
  code finds in the revealed text. UNCLEAR is accepted from any leader. SAFE is rejected when the
  text has a hard flag. Otherwise the validator runs both readings itself and must reach the same
  verdict word.

## Views

| Method | Returns |
|---|---|
| `verdict_of(rid: str) -> str` | `"SAFE"`, `"POISONED"`, `"UNCLEAR"`, or `""` for an unknown rid |
| `ruling_id(text_hash: str, kind: str, purpose: str, caps: str) -> str` | the rid, with the same normalisation as the writes |
| `lookup(text_hash, kind, purpose, caps) -> str` | the full ruling JSON, or `{"found": false, "rid"}` |
| `get_ruling(rid: str) -> str` | the full ruling: the summary fields plus `found`, `reason`, `requested_by`, `first_ruled_at`, `text` (revealed), `size` |
| `get_url(url: str) -> str` | the full ruling for the URL's latest fetch, plus `url` |
| `rulings_for_text(text_hash: str) -> str` | `{"text_hash", "items": [summary…]}`: every declaration this text was judged under |
| `list_rulings(offset: int, limit: int) -> str` | `{"total", "offset", "items": [summary…]}`, oldest first, `limit` ≤ 50 |
| `get_stats() -> str` | `{"rulings", "texts", "urls", "judged", "cached", "verdicts": {"SAFE", "POISONED", "UNCLEAR"}}` |
| `get_constants() -> str` | version, limits, kinds, capabilities, and the hard flags per kind |

## Flags

| Code | Meaning | Hard for |
|---|---|---|
| H1 | hidden characters (zero-width, bidi controls, Unicode tag characters, variation selectors outside emoji) | all kinds |
| H2 | a secret location next to a verb that moves data | all kinds |
| H3 | concealment from the user | all but `system-prompt` |
| H4 | instruction override, including `<IMPORTANT>`-style tags | all but `system-prompt` |
| H5 | wording addressed to a reviewer or judge | all kinds |
| S1 | a reference to a tool the text does not define | soft |
| S2 | a long text, an encoded blob, a link, or a non-JSON `mcp-tool` | soft |
| S3 | a side-channel parameter (`notes`, `context`, `metadata`…) that talks about files | soft |
| S4 | a mention of credentials | soft |

## Using it from a contract

```python
judge = gl.contract.get_at(gl.Address(JUDGE_ADDRESS)).view()
if judge.verdict_of(rid) != "SAFE":
    raise gl.vm.UserError("[EXPECTED] not ruled SAFE")
```

Cross-contract calls must be made outside non-deterministic blocks. See
`contracts/src/skill_directory.py`.
