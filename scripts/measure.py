"""Every number in the README.

    python scripts/measure.py

The headline is a negative result, so it is worth saying what would have been
reported instead. Comparing the registry's structured `minimumAge` against an
age floor parsed out of the eligibility prose produces a disagreement on 4.9%
of the trials that state both. That number is not a registry error rate, and
reporting it as one would be wrong by about a factor of ten.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trialmatch import corpus  # noqa: E402

LABELS = Path(__file__).resolve().parents[1] / "data" / "age_disagreement_labels.json"


def rule(title: str) -> None:
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


def the_corpus(trials) -> None:
    rule("the corpus")
    print(f"trials                      {len(trials):>7,}")
    structured = sum(1 for t in trials if t.structured_min_years is not None)
    prose = sum(1 for t in trials if t.stated_min_years is not None)
    print(f"with structured minimumAge  {structured:>7,}")
    print(f"with an age floor in prose  {prose:>7,}")
    phases = collections.Counter(p for t in trials for p in t.phases)
    print(f"phases                      {dict(phases.most_common(4))}")
    lengths = sorted(len(t.criteria) for t in trials)
    print(f"median criteria length      {lengths[len(trials) // 2]:>7,} chars")


def the_apparent_rate(trials) -> tuple[list, int]:
    rule("the number that is wrong")
    both = [
        t for t in trials
        if t.structured_min_years is not None and t.stated_min_years is not None
    ]
    disagree = [
        t for t in both if abs(t.structured_min_years - t.stated_min_years) > 0.01
    ]
    print(f"trials stating an age floor BOTH ways   {len(both):>6,}")
    print(f"where the two disagree                  {len(disagree):>6,}"
          f"   {len(disagree) / len(both):.1%}")
    print("\n  ^ this is the number a paper would report as a registry")
    print("    self-consistency rate. Every line below is about why it is not one.")
    return disagree, len(both)


def the_audit(disagree, n_both: int) -> None:
    rule("what the disagreements actually are")
    blob = json.loads(LABELS.read_text(encoding="utf-8"))
    annotations = blob["annotations"]
    counts = collections.Counter(a["label"] for a in annotations)
    n = len(annotations)

    here = {t.nct_id for t in disagree}
    overlap = sum(1 for a in annotations if a["nct_id"] in here)
    print(f"hand-labelled sample of {n} disagreements, drawn from the 2026-09-21 pull")
    print(f"({overlap} of the {n} are among this corpus's {len(disagree)} disagreements;"
          " the fetch is live, so a later pull is a different slice):\n")
    for label, count in counts.most_common():
        print(f"  {count:>3}  {count / n:>5.1%}  {label}")

    real = counts["real"]
    print(f"\n  genuinely contradictory: {real}/{n} = {real / n:.1%}")
    print(f"  false positive rate:     {1 - real / n:.1%}")
    raw = len(disagree) / n_both
    print(f"\n  implied true rate: {raw:.1%} x {real / n:.1%}"
          f" = about {raw * real / n:.2%} of trials,")
    print(f"  not the {raw:.1%} the raw comparison reports.")


def the_reasons() -> None:
    rule("why an age in the criteria is usually not the trial's age floor")
    blob = json.loads(LABELS.read_text(encoding="utf-8"))
    for label, description in blob["labels"].items():
        if label == "real":
            continue
        print(f"\n  {label}")
        print(f"    {description}")
        example = next(
            (a for a in blob["annotations"] if a["label"] == label), None
        )
        if example:
            print(f"    e.g. {example['nct_id']}: {example['note']}")

    print("\n  ^ eligibility prose uses ages for many things and an entry")
    print("    requirement is only one of them. A pattern cannot tell which,")
    print("    because the distinction is in the surrounding sentence and")
    print("    sometimes in the sentence after it.")


def the_recoverable_part(trials) -> None:
    rule("what the structured fields are good for anyway")
    have = [t for t in trials if t.structured_min_years is not None]
    paediatric = [t for t in have if t.structured_min_years < 18]
    print(f"trials with a usable structured floor   {len(have):>6,}"
          f"   ({len(have) / len(trials):.0%} of the corpus)")
    print(f"  of those, open to under-18s           {len(paediatric):>6,}"
          f"   ({len(paediatric) / len(have):.0%})")
    claimed = [t for t in trials if t.sex_claimed_in_text]
    conflict = [
        t for t in claimed
        if t.sex != corpus.ALL and t.sex != t.sex_claimed_in_text
    ]
    print(f"\ntrials asserting a sex restriction in prose {len(claimed):>5,}")
    print(f"  where the structured sex field differs    {len(conflict):>5,}")
    print("\n  ^ the structured fields are the ones to match on. They are present")
    print("    on 97% of trials, they are typed, and nothing has to be parsed out")
    print("    of a sentence to use them.")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not corpus.available():
        print(f"no corpus at {corpus.trials_path()}.\n"
              "Run `python scripts/fetch_trials.py` first "
              f"(or set {corpus.DATA_ENV} to a directory holding trials.json).",
              file=sys.stderr)
        return 2
    trials = corpus.load()
    the_corpus(trials)
    disagree, n_both = the_apparent_rate(trials)
    the_audit(disagree, n_both)
    the_reasons()
    the_recoverable_part(trials)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
