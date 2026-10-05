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
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: Set this to a directory holding ``trials.json`` to read the corpus from
#: somewhere other than the repository's own ``data/``.
DATA_ENV = "TRIALMATCH_DATA"
REPO_DATA = Path(__file__).resolve().parents[2] / "data"


def data_dir() -> Path:
    """Where ``trials.json`` lives: ``$TRIALMATCH_DATA`` if set, else ``<repo>/data``."""
    override = os.environ.get(DATA_ENV, "").strip()
    return Path(override) if override else REPO_DATA


def trials_path() -> Path:
    return data_dir() / "trials.json"


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


def available(path: str | Path | None = None) -> bool:
    """True when the corpus file exists, so callers can skip instead of crash."""
    return (Path(path) if path else trials_path()).is_file()


def load(path: str | Path | None = None) -> tuple[Trial, ...]:
    """Load the corpus from ``path``, or from :func:`trials_path` when omitted."""
    return _load(str(Path(path) if path else trials_path()))


@lru_cache(maxsize=4)
def _load(target_str: str) -> tuple[Trial, ...]:
    target = Path(target_str)
    if not target.is_file():
        raise TrialsMissingError(
            f"{target} is missing. Run `python scripts/fetch_trials.py` (the API is "
            f"public and needs no key), or set {DATA_ENV} to a directory holding "
            "trials.json."
        )
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        rows = raw["trials"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(
            f"{target} is not a trial-match corpus ({exc!s}). Re-run scripts/fetch_trials.py."
        ) from exc
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
        for t in rows
    )


def structurally_eligible(
    trials: tuple[Trial, ...] | list[Trial], age_years: float, sex: str = ALL
) -> list[Trial]:
    """Trials whose *structured* age range and sex field admit this person.

    This is the matching the README recommends: typed fields only, no prose.
    A blank structured bound is treated as open. ``sex`` is ``"FEMALE"``,
    ``"MALE"`` or ``"ALL"`` (match regardless of sex restriction).
    """
    if isinstance(age_years, bool) or not isinstance(age_years, (int, float)):
        raise TypeError(f"age_years must be a number, got {type(age_years).__name__}")
    if not 0 <= age_years < 130:
        raise ValueError(f"age_years must be between 0 and 130, got {age_years}")
    sex = (sex or ALL).upper()
    if sex not in (ALL, FEMALE, MALE):
        raise ValueError(f"sex must be FEMALE, MALE or ALL, got {sex!r}")
    out = []
    for t in trials:
        low, high = t.structured_min_years, t.structured_max_years
        if low is not None and age_years < low:
            continue
        if high is not None and age_years > high:
            continue
        if sex != ALL and t.sex not in ("", ALL, sex):
            continue
        out.append(t)
    return out
