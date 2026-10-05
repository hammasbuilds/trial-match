"""Against the real 12,500-trial pull from ClinicalTrials.gov.

Most of these guard the age parser, because it is the part that has already
been wrong twice and both times the wrongness showed up as a plausible-looking
percentage rather than as a crash.
"""

from __future__ import annotations

import pytest

from trialmatch import corpus


def test_corpus_size(trials):
    assert len(trials) == 12_500


def test_every_trial_has_an_id_and_criteria(trials):
    assert all(t.nct_id.startswith("NCT") for t in trials)
    assert all(t.criteria.strip() for t in trials)


def test_ids_are_unique(trials):
    assert len({t.nct_id for t in trials}) == len(trials)


def test_structured_age_is_present_on_almost_every_trial(trials):
    """97%. The README leans on this, so it is asserted."""
    have = sum(1 for t in trials if t.structured_min_years is not None)
    assert have / len(trials) > 0.95


@pytest.mark.parametrize(
    "raw,years",
    [("18 Years", 18.0), ("6 Months", 0.5), ("1 Year", 1.0), ("", None), ("N/A", None)],
)
def test_structured_age_units(raw, years):
    trial = corpus.Trial(
        nct_id="NCT0",
        title="",
        status="",
        phases=(),
        enrollment=None,
        conditions=(),
        criteria="",
        min_age=raw,
        max_age="",
        sex=corpus.ALL,
        healthy_volunteers=None,
    )
    got = trial.structured_min_years
    assert got == pytest.approx(years) if years is not None else got is None


def test_stage_is_not_read_as_age():
    """The bug that produced a 6.3% contradiction rate out of nothing.

    Without word boundaries, `age` matched inside 'stage', so 'Lymphedema
    stage >= 2' parsed as an age floor of two years and disagreed loudly with
    a structured minimum of 18.
    """
    trial = corpus.Trial(
        nct_id="NCT0",
        title="",
        status="",
        phases=(),
        enrollment=None,
        conditions=(),
        criteria="Lymphedema stage >= 2 at screening",
        min_age="18 Years",
        max_age="",
        sex=corpus.ALL,
        healthy_volunteers=None,
    )
    assert trial.stated_min_years is None


@pytest.mark.parametrize(
    "text",
    [
        "Percentage >= 5 years of growth",
        "Dosage of at least 10 years worth",
        "Tumour stage >= 3 years after diagnosis",
    ],
)
def test_words_containing_age_are_not_age_floors(text):
    trial = corpus.Trial(
        nct_id="NCT0",
        title="",
        status="",
        phases=(),
        enrollment=None,
        conditions=(),
        criteria=text,
        min_age="18 Years",
        max_age="",
        sex=corpus.ALL,
        healthy_volunteers=None,
    )
    assert trial.stated_min_years is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Age >= 18 years", 18),
        ("Patients aged 65 years or older", 65),
        ("Subjects 12 years of age and older", 12),
        ("aged at least 21 years", 21),
    ],
)
def test_plain_age_floors_are_read(text, expected):
    trial = corpus.Trial(
        nct_id="NCT0",
        title="",
        status="",
        phases=(),
        enrollment=None,
        conditions=(),
        criteria=text,
        min_age="18 Years",
        max_age="",
        sex=corpus.ALL,
        healthy_volunteers=None,
    )
    assert trial.stated_min_years == expected


def test_implausible_ages_are_rejected():
    trial = corpus.Trial(
        nct_id="NCT0",
        title="",
        status="",
        phases=(),
        enrollment=None,
        conditions=(),
        criteria="aged >= 900 years",
        min_age="",
        max_age="",
        sex=corpus.ALL,
        healthy_volunteers=None,
    )
    assert trial.stated_min_years is None


def test_prose_age_floor_is_found_on_a_minority(trials):
    """Only ~21% of trials state an age floor in prose at all.

    Worth pinning: if a future loosening of the pattern pushed this towards
    100%, it would be matching ages that are not floors, which is exactly the
    failure the repository documents.
    """
    share = sum(1 for t in trials if t.stated_min_years is not None) / len(trials)
    assert 0.10 < share < 0.35
