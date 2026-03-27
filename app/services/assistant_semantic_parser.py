import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime


DATE_PATTERNS = (
    re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\b"),
    re.compile(r"\b(?P<d>\d{2})/(?P<m>\d{2})/(?P<y>\d{4})\b"),
)
TRANSFER_REFERENCE_PATTERN = re.compile(r"\bEXT-[A-Z0-9]{4,}\b", re.IGNORECASE)


@dataclass(slots=True)
class SemanticQuery:
    domain: str
    raw_message: str
    normalized_message: str
    tokens: set[str]
    action: str = "unknown"
    subject: str | None = None
    explanation_mode: str | None = None
    reference_code: str | None = None
    exact_date: date | None = None
    date_from: date | None = None
    date_to: date | None = None
    qualifiers: list[str] = field(default_factory=list)
    matched_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "action": self.action,
            "subject": self.subject,
            "explanation_mode": self.explanation_mode,
            "reference_code": self.reference_code,
            "exact_date": self.exact_date.isoformat() if self.exact_date else None,
            "date_from": self.date_from.isoformat() if self.date_from else None,
            "date_to": self.date_to.isoformat() if self.date_to else None,
            "qualifiers": list(self.qualifiers),
            "matched_signals": list(self.matched_signals),
        }


def normalize_text(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def tokenize(normalized_message: str) -> set[str]:
    cleaned = re.sub(r"[^\w/+:-]+", " ", normalized_message)
    return {token for token in cleaned.split() if token}


def extract_single_date(message: str) -> date | None:
    normalized = normalize_text(message)
    for pattern in DATE_PATTERNS:
        match = pattern.search(normalized)
        if not match:
            continue
        try:
            return datetime(
                year=int(match.group("y")),
                month=int(match.group("m")),
                day=int(match.group("d")),
            ).date()
        except ValueError:
            return None
    return None


def extract_date_range(message: str) -> tuple[date | None, date | None]:
    normalized = normalize_text(message)
    matches: list[date] = []
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(normalized):
            try:
                matches.append(
                    datetime(
                        year=int(match.group("y")),
                        month=int(match.group("m")),
                        day=int(match.group("d")),
                    ).date()
                )
            except ValueError:
                continue
    if not matches:
        return None, None
    if len(matches) == 1:
        return matches[0], matches[0]
    ordered = sorted(matches)
    return ordered[0], ordered[-1]


def extract_transfer_reference(message: str) -> str | None:
    match = TRANSFER_REFERENCE_PATTERN.search(str(message or ""))
    if not match:
        return None
    return str(match.group(0)).upper()


def has_any_term(normalized_message: str, terms: set[str]) -> bool:
    return any(term in normalized_message for term in terms)
