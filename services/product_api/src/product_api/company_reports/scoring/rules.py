from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Final, Mapping

from product_api.company_reports.signals.models import (
    SignalCategory,
    SignalDirection,
    SignalStrength,
)


SCORING_RULESET_VERSION: Final = "1"
CATEGORY_ORDER: Final = {
    SignalCategory.LEGAL_STATUS: 0,
    SignalCategory.FINANCIAL: 1,
    SignalCategory.ARBITRATION: 2,
}
CATEGORY_CAPS: Final = MappingProxyType(
    {
        SignalCategory.LEGAL_STATUS: (Decimal("-8"), Decimal("3")),
        SignalCategory.FINANCIAL: (Decimal("-8"), Decimal("0")),
        SignalCategory.ARBITRATION: (Decimal("-5"), Decimal("1")),
    }
)
MAX_QUALITY_POINTS: Final = 52
QUALITY_HIGH_OR_CLEAN: Final = 4
QUALITY_MEDIUM: Final = 3
CONFLICT_MULTIPLIER: Final = Decimal("0.5")
MINIMUM_CONFIDENCE: Final = Decimal("0.6500")
CONFIDENCE_QUANTUM: Final = Decimal("0.0001")


@dataclass(frozen=True)
class ScoringRule:
    code: str
    category: SignalCategory
    direction: SignalDirection
    allowed_strengths: frozenset[SignalStrength]
    weights: Mapping[SignalStrength, Decimal]

    def weight_for(self, strength: SignalStrength) -> Decimal:
        try:
            return self.weights[strength]
        except KeyError as exc:
            raise ValueError("signal strength is not registered for scoring rule") from exc


def _rule(
    code: str,
    category: SignalCategory,
    direction: SignalDirection,
    weights: dict[SignalStrength, str],
) -> ScoringRule:
    frozen_weights = MappingProxyType(
        {strength: Decimal(weight) for strength, weight in weights.items()}
    )
    return ScoringRule(
        code=code,
        category=category,
        direction=direction,
        allowed_strengths=frozenset(frozen_weights),
        weights=frozen_weights,
    )


SCORING_RULE_REGISTRY: Final = MappingProxyType(
    {
        "counterparty.active": _rule(
            "counterparty.active",
            SignalCategory.LEGAL_STATUS,
            SignalDirection.POSITIVE,
            {SignalStrength.MEDIUM: "2"},
        ),
        "counterparty.dissolved": _rule(
            "counterparty.dissolved",
            SignalCategory.LEGAL_STATUS,
            SignalDirection.NEGATIVE,
            {SignalStrength.CRITICAL: "-8"},
        ),
        "counterparty.long_operating_history": _rule(
            "counterparty.long_operating_history",
            SignalCategory.LEGAL_STATUS,
            SignalDirection.POSITIVE,
            {SignalStrength.LOW: "1"},
        ),
        "counterparty.status_conflict": _rule(
            "counterparty.status_conflict",
            SignalCategory.LEGAL_STATUS,
            SignalDirection.INFORMATIONAL,
            {SignalStrength.HIGH: "0"},
        ),
        "finance.negative_equity": _rule(
            "finance.negative_equity",
            SignalCategory.FINANCIAL,
            SignalDirection.NEGATIVE,
            {SignalStrength.HIGH: "-4"},
        ),
        "finance.revenue_decline": _rule(
            "finance.revenue_decline",
            SignalCategory.FINANCIAL,
            SignalDirection.NEGATIVE,
            {SignalStrength.MEDIUM: "-2"},
        ),
        "finance.net_loss": _rule(
            "finance.net_loss",
            SignalCategory.FINANCIAL,
            SignalDirection.NEGATIVE,
            {SignalStrength.MEDIUM: "-2"},
        ),
        "finance.cash_shortfall": _rule(
            "finance.cash_shortfall",
            SignalCategory.FINANCIAL,
            SignalDirection.NEGATIVE,
            {
                SignalStrength.MEDIUM: "-2",
                SignalStrength.HIGH: "-4",
            },
        ),
        "finance.high_accounts_payable": _rule(
            "finance.high_accounts_payable",
            SignalCategory.FINANCIAL,
            SignalDirection.NEGATIVE,
            {SignalStrength.HIGH: "-3"},
        ),
        "arbitration.high_respondent_case_count": _rule(
            "arbitration.high_respondent_case_count",
            SignalCategory.ARBITRATION,
            SignalDirection.NEGATIVE,
            {SignalStrength.HIGH: "-3"},
        ),
        "arbitration.respondent_case_growth": _rule(
            "arbitration.respondent_case_growth",
            SignalCategory.ARBITRATION,
            SignalDirection.NEGATIVE,
            {SignalStrength.MEDIUM: "-2"},
        ),
        "arbitration.open_cases": _rule(
            "arbitration.open_cases",
            SignalCategory.ARBITRATION,
            SignalDirection.NEGATIVE,
            {SignalStrength.MEDIUM: "-1"},
        ),
        "arbitration.frequent_plaintiff": _rule(
            "arbitration.frequent_plaintiff",
            SignalCategory.ARBITRATION,
            SignalDirection.POSITIVE,
            {SignalStrength.MEDIUM: "1"},
        ),
    }
)


def rule_for_code(code: str) -> ScoringRule:
    try:
        return SCORING_RULE_REGISTRY[code]
    except KeyError as exc:
        raise ValueError("signal code is not registered for scoring") from exc


def dataset_for_code(code: str) -> str:
    rule_for_code(code)
    return code.split(".", maxsplit=1)[0]


__all__ = [
    "CATEGORY_CAPS",
    "CATEGORY_ORDER",
    "CONFIDENCE_QUANTUM",
    "CONFLICT_MULTIPLIER",
    "MAX_QUALITY_POINTS",
    "MINIMUM_CONFIDENCE",
    "QUALITY_HIGH_OR_CLEAN",
    "QUALITY_MEDIUM",
    "SCORING_RULESET_VERSION",
    "SCORING_RULE_REGISTRY",
    "ScoringRule",
    "dataset_for_code",
    "rule_for_code",
]
