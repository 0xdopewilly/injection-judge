# Review response: UNCLEAR must be reproduced, and nothing unverified is stored

## v3: the model's reason is no longer stored (2026-10-19, before re-review)

v2 fixed the finding below, but one gap of the same kind remained. Validators reproduced the verdict
word and code checked a POISONED quote, yet the leader's free-text `reason` was stored with every
ruling without any validator comparing it. A leader could put any sentence into a ruling that other
contracts and readers rely on.

- `lib/verdict.py`: `verified_ruling(result, hard)` keeps the reproduced verdict, the code-checked
  quote (POISONED only) and a fixed reason derived from those facts: one sentence per verdict, and
  for UNCLEAR under hard flags, the hard-flag sentence. The leader's own reason is dropped.
- `contracts/src/injection_judge.py`: `_judge` returns `verified_ruling(gl.vm.run_nondet(...))`, so
  only verified data reaches storage. `CONTRACT_VERSION` is now "3".
- Tests: `tests/test_verdict.py::test_a_ruling_stores_only_verified_facts`;
  `tests/direct/test_injection_judge.py::test_poisoned_needs_a_quote_that_is_in_the_text` (a model
  reason saying "IGNORE THE RULES" never reaches the stored ruling) and
  `test_hard_flags_make_safe_impossible` (the stored reason is the hard-flag sentence). 40 passed.

Live as v3 at `0x2Ff8E797DbcB373D463b1e3FAd1d7A72496c4660` (source `4764d097…eaf5`, commit `43d92da`),
with SkillDirectory v3 at `0xF8E75DBeAfce2B460843B25fF67ccF157e0e82ac`. The same 15 calls were replayed
([DEPLOYMENTS.md](DEPLOYMENTS.md)). The strict rule is visible on chain: the ambiguous system prompt
was twice UNDETERMINED, because the leader said UNCLEAR and most validators, judging for themselves,
did not. Nothing was stored either time. A later attempt reached SAFE by agreement.

## v2: UNCLEAR must be reproduced

### The finding

> The contract cannot be accepted because validators automatically approve any structurally valid
> UNCLEAR verdict without independently checking it. This lets UNCLEAR pass even when the same
> validator would derive SAFE or POISONED, while that verdict controls finality and downstream
> eligibility.

Correct. In v1, `_judge`'s validator returned `True` for any structurally valid UNCLEAR ruling.

### The fix (commit `76792f1`, deployed as v2)

- `contracts/src/injection_judge.py`: the validator always runs its own two readings and accepts only
  if its verdict word equals the leader's. UNCLEAR is checked like SAFE and POISONED, so a leader can
  neither hide a POISONED or SAFE text behind UNCLEAR nor block a ruling by claiming it.
- `lib/verdict.py`: SAFE and UNCLEAR readings carry no quote, and `claim_valid` rejects a SAFE or
  UNCLEAR ruling that has one. Only POISONED stores evidence, and code must find that quote in the
  revealed text. Nothing unverified rides on a verdict.

Hard red flags still make SAFE impossible, and UNCLEAR can still be judged again up to three times;
each of those attempts must now be reproduced too.

### Tests

- `tests/direct/test_injection_judge.py::test_validator_rules`: a validator whose own readings say SAFE
  rejects a leader's UNCLEAR; one whose readings say POISONED rejects both SAFE and UNCLEAR.
- `test_unclear_must_be_reproduced`: UNCLEAR is accepted only by a validator whose own readings also end
  in UNCLEAR, never with a quote attached, and refused by a validator whose readings say SAFE.
- `tests/test_verdict.py`: SAFE and UNCLEAR parse to an empty quote; `claim_valid` rejects quotes on them.

`GENVM_VERSION=v0.6.0-rc5 .venv/bin/python -m pytest -q`: 39 passed.

### Live on Studio Next

v2 at `0x4d938096e549fc900Db9Af72ac0d0aF168e5D482` with a new SkillDirectory at
`0x71c0006Df02839B2030a780151bda2727045f6dA`. The 15 calls of the v1 run were replayed unchanged, and all
are FINALIZED ([DEPLOYMENTS.md](DEPLOYMENTS.md)):

- The ambiguous system prompt is UNCLEAR three times, reproduced by the validators each time, then final.
- Two texts v1 parked at UNCLEAR now reach POISONED by agreement: concealment wording judged as a skill,
  and a skill that addresses the judge.
- Exfiltration in a tool and in a fetched skill: POISONED with verified quotes. A benign tool, an honest
  skill and Anthropic's pdf skill: SAFE. SkillDirectory lists the SAFE skills and refuses the poisoned one.

The deployed code's SHA-256 (`0f621760ee95282d1e87821883c0c5ff07f5bda2e3e4d341da54d9857eea3e9b`) is read from
the deploy transaction in [evidence/transactions.md](evidence/transactions.md) and equals
`git show 76792f1:contracts/injection_judge.py | sha256sum`.
