"""The hand-labelled audit has to describe the corpus it claims to describe.

The README's headline is a ratio computed from this file, so a label file that
drifted out of sync with the corpus — a trial that no longer exists, a count
that no longer matches the annotations, a category invented in the prose and
never used — would quietly change the headline.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

import pytest

LABELS = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "age_disagreement_labels.json")
    .read_text(encoding="utf-8")
)
ANNOTATIONS = LABELS["annotations"]


def test_counts_match_the_annotations():
    """The summary block is derived, so it must not be edited by hand.

    It was, once: the file shipped saying 48 when it held 49, and one of the
    49 was an id invented to record a second reading of a trial already in the
    list.
    """
    counted = collections.Counter(a["label"] for a in ANNOTATIONS)
    declared = {k: v for k, v in LABELS["counts"].items() if k != "total"}
    assert dict(counted) == declared
    assert LABELS["counts"]["total"] == len(ANNOTATIONS)


def _labelled_in(trials) -> list[tuple[dict, object]]:
    by_id = {t.nct_id: t for t in trials}
    return [(a, by_id[a["nct_id"]]) for a in ANNOTATIONS if a["nct_id"] in by_id]


def test_every_labelled_trial_exists_in_the_corpus(trials):
    """Catches invented ids, against the snapshot the labels were drawn from.

    The fetch is live: a later pull returns a different slice of recruiting
    trials, so on any other corpus this cannot tell an invented id from a trial
    that is simply not in today's slice, and it skips rather than guess.
    """
    present = _labelled_in(trials)
    if len(present) < len(ANNOTATIONS):
        pytest.skip(
            f"corpus is a different registry snapshot: {len(present)} of "
            f"{len(ANNOTATIONS)} labelled trials are in it"
        )
    assert len(present) == len(ANNOTATIONS)


def test_no_trial_is_labelled_twice():
    ids = [a["nct_id"] for a in ANNOTATIONS]
    assert [k for k, v in collections.Counter(ids).items() if v > 1] == []


def test_every_label_is_documented():
    used = {a["label"] for a in ANNOTATIONS}
    assert used <= set(LABELS["labels"])


def test_every_documented_label_is_used():
    """An unused category in the taxonomy is a category that was guessed."""
    used = {a["label"] for a in ANNOTATIONS}
    assert set(LABELS["labels"]) <= used


def test_every_annotation_has_a_note():
    """The note is the evidence. Without it the label is an assertion."""
    assert all(a.get("note", "").strip() for a in ANNOTATIONS)


def test_recorded_values_match_the_corpus(trials):
    """The structured and prose ages in the label file are not retyped facts.

    If they disagree with what the parser now produces, either the parser
    changed or the labels were transcribed wrongly, and the audit is measuring
    something other than what it says.
    """
    present = _labelled_in(trials)
    if not present:
        pytest.skip("none of the labelled trials is in this corpus")
    for a, trial in present:
        assert trial.structured_min_years == a["structured"], a["nct_id"]
        assert trial.stated_min_years == a["prose"], a["nct_id"]


def test_every_labelled_trial_really_disagrees(trials):
    """The sample is drawn from disagreements, so all of them must be ones."""
    present = _labelled_in(trials)
    if not present:
        pytest.skip("none of the labelled trials is in this corpus")
    for _, trial in present:
        assert abs(trial.structured_min_years - trial.stated_min_years) > 0.01


def test_most_disagreements_are_false_positives():
    """The finding itself. If this ever flips, the README is wrong."""
    real = sum(1 for a in ANNOTATIONS if a["label"] == "real")
    assert real / len(ANNOTATIONS) < 0.25
