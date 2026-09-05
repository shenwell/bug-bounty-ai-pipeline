"""Tests for contract scoring."""

from unittest.mock import MagicMock, patch

import pytest

from portfolio.common.models import Asset, Contract, ProgramConstraints, ProgramFormat, RewardRange
from portfolio.scoring.scorer import ContractScorer


@pytest.fixture
def scorer(config):
    with patch("portfolio.scoring.scorer.LLMProviderFactory.create") as mock_factory:
        mock_llm = MagicMock()
        mock_llm.complete_json.return_value = {
            "adjustment": 1.0,
            "vectors": ["sqli"],
            "mismatch": "",
        }
        mock_factory.return_value = mock_llm
        yield ContractScorer(config)


def test_score_classic(scorer):
    contract = Contract(
        program_id="p1",
        slug="test",
        name="Test",
        scope=["api.example.com"],
        assets=[Asset(identifier="api.example.com", engagement_profile="web_api")],
        reward_ranges=[RewardRange(severity="high", max_amount=100000)],
        constraints=ProgramConstraints(),
    )
    result = scorer.score(contract)
    assert result.score is not None
    assert 0 <= result.score <= 1.0


def test_should_hunt_unpaid(scorer):
    contract = Contract(
        program_id="p1",
        slug="unpaid",
        name="Unpaid",
        score=0.9,
        is_paid=False,
    )
    assert scorer.should_hunt(contract) is False


def test_score_unpaid(scorer):
    contract = Contract(
        program_id="p1",
        slug="unpaid",
        name="Unpaid",
        is_paid=False,
        scope=["api.example.com"],
        reward_ranges=[RewardRange(severity="high", max_amount=100000)],
    )
    result = scorer.score(contract)
    assert result.score == 0.0
    assert "unpaid_contract" in result.score_reason


def test_should_hunt(scorer):
    contract = Contract(
        program_id="p1",
        slug="test",
        name="Test",
        score=0.8,
        requires_accept_rules=True,
        accept_rules_pending=True,
    )
    assert scorer.should_hunt(contract) is False


def test_score_nte(scorer):
    contract = Contract(
        program_id="p1",
        slug="nte-test",
        name="NTE Program",
        program_format=ProgramFormat.NTE,
        acceptance_criteria="Achieve non-tolerable event",
        scope=["target.example.com"],
        assets=[Asset(identifier="target.example.com")],
    )
    result = scorer.score(contract)
    assert "NTE" in result.score_reason

