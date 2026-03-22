from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class LawInfo:
    law_id: str
    law_name: str


LAW_REGISTRY: list[LawInfo] = [
    LawInfo("N0030001", "勞動基準法"),
    LawInfo("N0030002", "勞工請假規則"),
    LawInfo("N0030003", "大量解僱勞工保護法"),
    LawInfo("N0030014", "勞資爭議處理法"),
    LawInfo("N0030015", "性別平等工作法"),
    LawInfo("N0050001", "勞工保險條例"),
    LawInfo("N0060001", "勞工退休金條例"),
    LawInfo("N0060002", "職業安全衛生法"),
    LawInfo("N0060003", "勞工職業災害保險及保護法"),
    LawInfo("N0090001", "就業保險法"),
    LawInfo("N0090003", "就業服務法"),
]

VALID_LAW_IDS: frozenset[str] = frozenset(law.law_id for law in LAW_REGISTRY)

BASE_URL = (
    "https://raw.githubusercontent.com/kong0107/mojLawSplitJSON"
    "/gh-pages/FalVMingLing/{law_id}.json"
)


def get_law_by_id(law_id: str) -> LawInfo | None:
    return next((law for law in LAW_REGISTRY if law.law_id == law_id), None)
