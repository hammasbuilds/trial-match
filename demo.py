"""What trial-match shows, in one command.

    python demo.py

Works on a fresh clone. Without the corpus it runs the age parser on a handful
of real eligibility sentences from the hand audit (data/age_disagreement_labels.json
is in git) and shows why a parsed "minimum age" is usually not one. With the
corpus (``python scripts/fetch_trials.py`` or ``$TRIALMATCH_DATA``) it also
matches an example patient on the structured fields.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from trialmatch import corpus  # noqa: E402

LABELS = Path(__file__).resolve().parent / "data" / "age_disagreement_labels.json"

# Sentences quoted in the README, each from the trial named, with the structured
# minimumAge that trial registered.
EXAMPLES = [
    (
        "NCT05667506",
        "Karnofsky (age >= 16 years) or Lansky (age < 16 years) performance status",
        "3 Years",
    ),
    ("NCT06507072", "Parents 18 years and older", "6 Years"),
    ("NCT07103395", "aged 18 to 75 years or older", "18 Years"),
    ("synthetic", "Lymphedema stage >= 2 at screening", "18 Years"),
    ("synthetic", "Patients aged 65 years or older", "65 Years"),
]


def _trial(nct: str, text: str, min_age: str) -> corpus.Trial:
    return corpus.Trial(
        nct_id=nct,
        title="",
        status="",
        phases=(),
        enrollment=None,
        conditions=(),
        criteria=text,
        min_age=min_age,
        max_age="",
        sex=corpus.ALL,
        healthy_volunteers=None,
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("1. Parsing an age floor out of eligibility prose\n")
    print(f"   {'trial':<12} {'structured':>10} {'parsed':>7}  sentence")
    for nct, text, min_age in EXAMPLES:
        t = _trial(nct, text, min_age)
        parsed = t.stated_min_years
        print(f"   {nct:<12} {t.structured_min_years:>10g} {parsed if parsed else '-':>7}  {text}")
    print("\n   The parser reads 16, 18 and 75 above, and none of them is the trial's floor.")

    blob = json.loads(LABELS.read_text(encoding="utf-8"))
    counts = collections.Counter(a["label"] for a in blob["annotations"])
    n = sum(counts.values())
    print(f"\n2. Hand audit of {n} prose-vs-structured disagreements (in git)\n")
    for label, k in counts.most_common():
        print(f"   {k:>3}  {k / n:>6.1%}  {label}")
    print(f"\n   Only {counts['real']}/{n} are real registry contradictions.")

    print("\n3. Matching on the structured fields\n")
    if not corpus.available():
        print(f"   skipped: no corpus at {corpus.trials_path()}.")
        print("   Run `python scripts/fetch_trials.py` (public API, no key, ~30 MB),")
        print(f"   or set {corpus.DATA_ENV} to a directory holding trials.json.")
        return 0
    trials = corpus.load()
    for age, sex in [(15, corpus.FEMALE), (70, corpus.MALE)]:
        hits = corpus.structurally_eligible(trials, age, sex)
        print(f"   {sex.lower()}, {age}: {len(hits):,} of {len(trials):,} recruiting trials admit")
        for t in hits[:3]:
            print(f"      {t.nct_id}  {t.title[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
