"""Contract scoring — deterministic + LLM competency assessment."""

from __future__ import annotations

from portfolio.agents.llm import LLMProviderFactory
from portfolio.common.config import AppConfig
from portfolio.common.logging import get_logger
from portfolio.common.models import Contract, ProgramFormat
from portfolio.routing.profiles import PROFILE_REGISTRY

logger = get_logger(__name__)

SUPPORTED_VECTORS = {
    "sqli", "xss", "ssrf", "idor", "authz", "jwt", "api", "graphql",
}

WEB_INDICATORS = {"http", "api", "web", "rest", "graphql", ".ru", ".com"}


class ContractScorer:
    def __init__(self, config: AppConfig):
        self._config = config
        self._weights = config.scoring.weights
        self._min_score = config.scoring.min_score_to_hunt
        self._llm = LLMProviderFactory.create(config)

    def score(self, contract: Contract) -> Contract:
        if not contract.is_paid:
            contract.score = 0.0
            contract.score_reason = "unpaid_contract: no monetary reward — dismissed"
            contract.target_vectors = []
            logger.info("contract_dismissed_unpaid", slug=contract.slug)
            return contract
        if contract.program_format == ProgramFormat.NTE:
            return self._score_nte(contract)
        return self._score_classic(contract)

    def _score_classic(self, contract: Contract) -> Contract:
        reward_score = self._reward_component(contract)
        scope_score = self._scope_component(contract)
        competency_score = self._competency_component(contract)
        restrictions_score = self._restrictions_component(contract)

        w = self._weights
        deterministic = (
            reward_score * w.reward
            + scope_score * w.scope_size
            + competency_score * w.competency_match
            + restrictions_score * w.restrictions
        )

        llm_adjustment, vectors, mismatch = self._llm_assessment(contract)
        final = min(1.0, max(0.0, deterministic * llm_adjustment))

        contract.score = round(final, 4)
        contract.target_vectors = vectors
        contract.score_reason = (
            f"reward={reward_score:.2f} scope={scope_score:.2f} "
            f"competency={competency_score:.2f} restrictions={restrictions_score:.2f} "
            f"llm_adj={llm_adjustment:.2f}"
        )
        if mismatch:
            contract.score_reason += f"; mismatch: {mismatch}"
            contract.score = min(contract.score, 0.3)

        if contract.requires_accept_rules and contract.accept_rules_pending:
            contract.score_reason += "; accept_rules_pending (human gate)"

        if contract.disclosed_count:
            contract.score_reason += f"; disclosed_reports={contract.disclosed_count}"

        logger.info("contract_scored", slug=contract.slug, score=contract.score)
        return contract

    def _score_nte(self, contract: Contract) -> Contract:
        base = self._score_classic(contract)
        nte_bonus = 0.1 if contract.acceptance_criteria else 0.0
        if base.score is not None:
            base.score = min(1.0, base.score + nte_bonus)
        base.score_reason += "; NTE format scoring applied"
        return base

    def _reward_component(self, contract: Contract) -> float:
        if not contract.reward_ranges:
            return 0.3
        max_reward = max((r.max_amount for r in contract.reward_ranges), default=0)
        if max_reward <= 0:
            return 0.3
        return min(1.0, max(0.35, max_reward / 100_000))

    def _scope_component(self, contract: Contract) -> float:
        n = len(contract.scope) + len(contract.assets)
        if n == 0:
            return 0.0
        return min(1.0, n / 10)

    def _competency_component(self, contract: Contract) -> float:
        profiles = {a.engagement_profile for a in contract.assets if a.engagement_profile}
        if not profiles:
            return 0.5
        supported = sum(1 for p in profiles if p in PROFILE_REGISTRY and PROFILE_REGISTRY[p].autonomous)
        return supported / len(profiles) if profiles else 0.5

    def _restrictions_component(self, contract: Contract) -> float:
        penalty = 0.0
        c = contract.constraints
        if c.vpn_required:
            penalty += 0.05
        if c.allowed_rce_commands:
            penalty += 0.1
        if c.no_bulk_enumeration:
            penalty += 0.05
        if c.stop_after_container_escape:
            penalty += 0.05
        return max(0.0, 1.0 - penalty)

    def _llm_assessment(self, contract: Contract) -> tuple[float, list[str], str]:
        tabs_summary = ""
        if contract.tab_sections:
            tabs_summary = "\n".join(
                f"{k}: {v[:500]}" for k, v in list(contract.tab_sections.items())[:6]
            )
        prompt = (
            "Goal: maximize paid bug bounty earnings. Only pursue contracts with monetary rewards.\n"
            f"Program: {contract.name}\n"
            f"Paid program: {contract.is_paid}\n"
            f"Reward ranges: {[r.model_dump() for r in contract.reward_ranges]}\n"
            f"Acceptance criteria: {contract.acceptance_criteria[:2000]}\n"
            f"Scope: {contract.scope[:20]}\n"
            f"Tab excerpts:\n{tabs_summary[:3000]}\n"
            f"Supported attack classes: {SUPPORTED_VECTORS}\n"
            "Return JSON: {\"adjustment\": 0.0-1.2, \"vectors\": [\"sqli\",...], "
            "\"mismatch\": \"\"}"
        )
        try:
            result = self._llm.complete_json(
                [{"role": "user", "content": prompt}],
                actor="scoring",
            )
            adjustment = float(result.get("adjustment", 1.0))
            vectors = [v for v in result.get("vectors", []) if v in SUPPORTED_VECTORS]
            mismatch = str(result.get("mismatch", ""))
            return adjustment, vectors or list(SUPPORTED_VECTORS)[:3], mismatch
        except Exception as e:
            logger.warning("llm_scoring_fallback", error=str(e))
            return 1.0, list(SUPPORTED_VECTORS)[:3], ""

    def should_hunt(self, contract: Contract) -> bool:
        if not contract.is_paid:
            return False
        if contract.requires_accept_rules and contract.accept_rules_pending:
            return False
        return (contract.score or 0) >= self._min_score
