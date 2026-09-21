"""Recruiting clinical trials, as their sponsors actually wrote them.

12,500 interventional trials pulled from ClinicalTrials.gov's v2 API. Each
carries two descriptions of who may enrol, and that duplication is the point:

* **structured fields** — `minimumAge`, `maximumAge`, `sex`, `healthyVolunteers`
* **free text** — `eligibilityCriteria`, a bulleted inclusion and exclusion list
  written by the sponsor

The same facts, recorded twice, by the same people, in the same submission. So
they can be checked against each other with no model at all, and where they
disagree one of them is wrong. A registry that contradicts itself is a problem
for anyone matching patients to trials, and it is measurable before any
language model is involved.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"
TRIALS = DATA / "trials.json"

# "18 Years", "6 Months", "90 Days" — the registry's own age format.
_AGE = re.compile(r"(\d+)\s*(year|month|week|day)", re.I)
_PER_YEAR = {"year": 1.0, "month": 1 / 12, "week": 1 / 52, "day": 1 / 365}

# An age floor as a sponsor writes it in prose.
#
# The word boundaries are load-bearing. Without them `age` matches inside
# **st-age**, **percent-age** and **dos-age**, so "Lymphedema stage >= 2" was
# being read as an age floor of two years and disagreeing loudly with a
# structured minimum of 18. That single missing \b produced a 6.3%
# contradiction rate that was entirely this pattern's own doing.
#
# Even with boundaries this stays conservative: it must read as the trial's own
# entry requirement, so a bare number near the word "age" is not enough.
_TEXT_MIN_AGE = re.compile(
    r"\b(?:aged|age)\b\s*(?:of\s*)?(?:>=|≥|at least|greater than or equal to|"
    r"older than|minimum(?:\s+of)?)\s*(\d{1,3})\s*(?:years?|yrs?)\b"
    r"|\b(\d{1,3})\s*(?:years?|yrs?)\s*(?:of age\s*)?(?:or older|and older)\b",
    re.I,
)

FEMALE_ONLY = re.compile(
    r"\b(?:female[s]?\s+only|women\s+only|must be (?:a )?(?:female|woman))\b", re.I
)
MALE_ONLY = re.compile(r"\b(?:male[s]?\s+only|men\s+only|must be (?:a )?(?:male|man))\b", re.I)

ALL = "ALL"
FEMALE = "FEMALE"
MALE = "MALE"


class TrialsMissingError(FileNotFoundError):
    """The trial corpus is not on disk."""


@dataclass(frozen=True)
class Trial:
    nct_id: str
    title: str
    status: str
    phases: tuple[str, ...]
    enrollment: int | None
    conditions: tuple[str, ...]
    criteria: str
    min_age: str
    max_age: str
    sex: str
    healthy_volunteers: bool | None

    @property
    def structured_min_years(self) -> float | None:
        """`minimumAge` in years, or None when the sponsor left it blank."""
        return _years(self.min_age)

    @property
    def structured_max_years(self) -> float | None:
        return _years(self.max_age)

    @property
    def stated_min_years(self) -> int | None:
        """An age floor written in the criteria prose, if one is stated plainly."""
        found = _TEXT_MIN_AGE.search(self.criteria)
        if not found:
            return None
        raw = found.group(1) or found.group(2)
        age = int(raw)
        return age if 0 < age < 120 else None

    @property
    def sex_claimed_in_text(self) -> str | None:
        """A sex restriction the prose asserts, if it asserts one."""
        if FEMALE_ONLY.search(self.criteria):
            return FEMALE
        if MALE_ONLY.search(self.criteria):
            return MALE
        return None


def _years(raw: str) -> float | None:
    found = _AGE.search(raw or "")
    if not found:
        return None
    return int(found.group(1)) * _PER_YEAR[found.group(2).lower()]


@lru_cache(maxsize=1)
def load(path: str | None = None) -> tuple[Trial, ...]:
    target = Path(path) if path else TRIALS
    if not target.exists():
        raise TrialsMissingError(
            f"{target} is missing. Run scripts/fetch_trials.py — the API is "
            "public and needs no key."
        )
    raw = json.loads(target.read_text(encoding="utf-8"))
    return tuple(
        Trial(
            nct_id=t["nct_id"],
            title=t["title"],
            status=t["status"],
            phases=tuple(t.get("phases") or []),
            enrollment=t.get("enrollment"),
            conditions=tuple(t.get("conditions") or []),
            criteria=t["criteria"],
            min_age=t.get("min_age", ""),
            max_age=t.get("max_age", ""),
            sex=t.get("sex", ""),
            healthy_volunteers=t.get("healthy_volunteers"),
        )
        for t in raw["trials"]
    )
