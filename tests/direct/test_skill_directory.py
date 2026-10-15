"""Direct-mode tests for contracts/skill_directory.py, the example InjectionJudge consumer.

Direct mode does not execute cross-contract calls, so these tests replace the one function that
makes it (_judge_url_ruling) with a fake judge. The real call is exercised live on Studio Next
(docs/DEPLOYMENTS.md)."""

import sys

import pytest

CONTRACT = "contracts/skill_directory.py"
JUDGE = "0x" + "ab" * 20
URL = "https://skills.example.com/commit-helper/SKILL.md"


class FakeJudge:
    def __init__(self):
        self.rulings = {}

    def __call__(self, judge, url):
        assert judge == JUDGE
        return self.rulings.get(url, {"found": False, "url": url})

    def rule(self, url, verdict, kind="skill", rid="r1"):
        self.rulings[url] = {"found": True, "url": url, "rid": rid, "text_hash": "h-" + rid, "kind": kind,
                             "verdict": verdict, "purpose": "Writes commit messages.", "caps": "filesystem,shell"}


@pytest.fixture
def directory(direct_vm, direct_deploy, direct_alice, monkeypatch):
    contract = direct_deploy(CONTRACT, JUDGE)
    module = next(m for m in list(sys.modules.values()) if getattr(m, "SkillDirectory", None) is not None)
    fake = FakeJudge()
    monkeypatch.setattr(module, "_judge_url_ruling", fake)
    direct_vm.sender = direct_alice
    return contract, fake


def skills(contract) -> list:
    import json

    return json.loads(contract.get_skills())["items"]


def test_only_skills_ruled_safe_are_listed(directory):
    contract, judge = directory
    with pytest.raises(Exception, match="no ruling"):
        contract.list_skill(URL)
    judge.rule(URL, "POISONED")
    with pytest.raises(Exception, match="ruled this skill POISONED"):
        contract.list_skill(URL)
    judge.rule(URL, "UNCLEAR")
    with pytest.raises(Exception, match="UNCLEAR"):
        contract.list_skill(URL)
    judge.rule(URL, "SAFE", kind="system-prompt")
    with pytest.raises(Exception, match="not skill"):
        contract.list_skill(URL)
    judge.rule(URL, "SAFE")
    assert contract.list_skill(URL)["rid"] == "r1"
    assert skills(contract)[0]["listed"] is True and skills(contract)[0]["text_hash"] == "h-r1"


def test_recheck_delists_when_a_newer_fetch_is_not_safe(directory):
    contract, judge = directory
    judge.rule(URL, "SAFE")
    contract.list_skill(URL)
    judge.rule(URL, "SAFE", rid="r2")  # same URL, new content, still SAFE
    assert contract.recheck(URL)["listed"] is True and skills(contract)[0]["rid"] == "r2"
    judge.rule(URL, "POISONED", rid="r3")  # the URL now serves something else
    result = contract.recheck(URL)
    assert result["listed"] is False and "POISONED" in result["note"]
    assert skills(contract)[0]["listed"] is False
    with pytest.raises(Exception, match="not in the directory"):
        contract.recheck("https://other.example.com/SKILL.md")


def test_the_judge_address_is_checked(direct_deploy):
    with pytest.raises(Exception, match="judge must be"):
        direct_deploy(CONTRACT, "not-an-address")
