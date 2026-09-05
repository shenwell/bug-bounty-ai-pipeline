"""Lint final Standoff paste description block only (not drafts or internal notes)."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Other findings / internal tracking — never in platform description.
_OTHER_FINDING_RE = re.compile(
    r"\b(?:SUB|LEAD|FINDING|REPORT)-\d{2,}\b",
    re.IGNORECASE,
)
_CROSS_REF_PHRASES = (
    "связанный отчёт",
    "связанный отчет",
    "связанная уязвимость",
    "отдельно от sub",
    "отдельно от lead",
    "отдельная уязвимость",
    "тот же класс ошибок",
    "предыдущий отчёт",
    "предыдущий отчет",
    "duplicate of",
    "related report",
    "see also sub",
    "see also lead",
)
_INTERNAL_PATH_RE = re.compile(
    r"(?:^|[\s(])(?:evidence/|poc/|hunt/|reports/(?:drafts|submit)/|\bD:\\)",
    re.IGNORECASE | re.MULTILINE,
)

PASTE_SECTION_MARKER = "## Описание (скопировать целиком в поле «Описание»)"


@dataclass(frozen=True)
class SubmitLintIssue:
    rule: str
    message: str
    excerpt: str = ""


def extract_paste_body(markdown: str) -> str:
    """Return only the text that goes into the platform description field."""
    if PASTE_SECTION_MARKER not in markdown:
        return markdown.strip()
    _, body = markdown.split(PASTE_SECTION_MARKER, 1)
    return body.strip()


def lint_submit_description(
    text: str,
    *,
    lead_id: str | None = None,
) -> list[SubmitLintIssue]:
    """Return violations; empty list means OK for submit paste body."""
    issues: list[SubmitLintIssue] = []
    normalized_lead = lead_id.upper().replace("_", "-") if lead_id else None

    for match in _OTHER_FINDING_RE.finditer(text):
        token = match.group(0).upper().replace("_", "-")
        if normalized_lead and token == normalized_lead:
            continue
        issues.append(
            SubmitLintIssue(
                rule="no-other-findings",
                message=f"Не ссылаться на другие находки/отчёты: {token}",
                excerpt=_excerpt(text, match.start()),
            )
        )

    lower = text.lower()
    for phrase in _CROSS_REF_PHRASES:
        if phrase in lower:
            issues.append(
                SubmitLintIssue(
                    rule="no-cross-ref-phrases",
                    message=f"Убрать перекрёстную отсылку: «{phrase}»",
                    excerpt=phrase,
                )
            )

    for match in _INTERNAL_PATH_RE.finditer(text):
        issues.append(
            SubmitLintIssue(
                rule="no-internal-paths",
                message="Не указывать внутренние пути (evidence/, poc/, hunt/, reports/)",
                excerpt=_excerpt(text, match.start()),
            )
        )

    return issues


def lint_submit_paste_file(
    markdown: str,
    *,
    lead_id: str | None = None,
) -> list[SubmitLintIssue]:
    body = extract_paste_body(markdown)
    return lint_submit_description(body, lead_id=lead_id)


def _excerpt(text: str, pos: int, radius: int = 40) -> str:
    start = max(0, pos - radius)
    end = min(len(text), pos + radius)
    snippet = text[start:end].replace("\n", " ")
    return snippet.strip()
