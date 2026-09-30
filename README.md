# trial-match

> The registry appears to contradict itself on 4.9% of clinical trials. Hand-checking 48 of those disagreements, **43 are the checker's fault, not the registry's.**

**Status:** complete as a measurement. The finding is a negative result and it does not need
a language model to stand up — it is a reason to be careful with one. See
[What this means for a matcher](#what-this-means-for-a-matcher).

## The corpus

**12,500 interventional trials** pulled from
[ClinicalTrials.gov's v2 API](https://clinicaltrials.gov/data-api/api) — public, versioned,
no key. Every trial describes who may enrol **twice**, in the same submission, by the same
sponsor:

| | |
|---|---:|
| Trials | **12,500** |
| With a structured `minimumAge` | 12,116 (97%) |
| With an age floor stated in the prose | 2,657 (21%) |
| With both | 2,634 |
| Median criteria length | 1,236 chars |

That duplication is the asset. The same fact, recorded twice, by the same people — so it
can be checked with no model at all.

```
python scripts/fetch_trials.py --pages 40    # rebuild the corpus
python scripts/measure.py                    # every table below
python -m pytest                             # 28 tests
```

## Results

Parse an age floor out of the eligibility prose, compare it against the structured
`minimumAge`, and **128 of 2,634 trials disagree — 4.9%**.

That is the number a paper would report as a registry self-consistency rate. It is wrong by
about a factor of ten.

## What the disagreements actually are

48 of the 128 were read by hand and labelled in
[data/age_disagreement_labels.json](data/age_disagreement_labels.json), with a note on each
recording the sentence that decided it.

| Label | n | |
|---|---:|---:|
| `sub_condition` | 21 | 43.8% |
| `cohort_disjunction` | 12 | 25.0% |
| `about_another_person` | 7 | 14.6% |
| **`real`** | **5** | **10.4%** |
| `exclusion` | 2 | 4.2% |
| `range_tail` | 1 | 2.1% |

**False positive rate: 89.6%.** The implied true contradiction rate is 4.9% × 10.4% ≈
**0.5%**, not 4.9%.

## Why an age in the criteria is usually not the trial's age floor

Eligibility prose uses ages for many things, and an entry requirement is only one of them.

**`sub_condition`** — the age gates some *other* criterion.
> `NCT05667506` — "Karnofsky (age ≥ 16 years) or Lansky (age < 16 years) performance status"
> — which scale to score on.
> `NCT07580586` — "Female participants 50 years of age or older, in menopause for 24
> consecutive months" — how menopause is defined.
> `NCT04700826` — "Heart failure; Hypertension; Age 65 years or older; Diabetes" — a
> CHA₂DS₂-VASc risk-factor list.

**`cohort_disjunction`** — one of several alternative routes in.
> `NCT05245656` — "age ≥70 years, or 60-69 years if the patients are ineligible for…"
> `NCT04248569` — "Cohort C: Patients must be Age ≥ 18".

**`about_another_person`** — the age belongs to a parent, guardian, caregiver or donor.
> `NCT06507072` — "Parents 18 years and older", in a paediatric trial with `minimumAge` 6.
> `NCT02982902` — "Age ≥ 18 years" inside the *donor* selection criteria; the patient
> minimum is three months.

**`range_tail`** — the pattern matched the top of a range.
> `NCT07103395` — "aged 18 to 75 years or older".

The distinction is never in the matched phrase. It is in the surrounding sentence, and
sometimes in the sentence after it.

## The bug before this one

An earlier version of the same pattern reported a **6.3%** contradiction rate. It had no
word boundary around `age`, so it matched inside **st·age**, **percent·age** and
**dos·age**: "Lymphedema stage ≥ 2" parsed as an age floor of two years and disagreed
loudly with a structured minimum of 18.

Both that bug and this one produced a plausible-looking percentage rather than a crash,
which is the only reason either survived long enough to be worth writing down.
`test_stage_is_not_read_as_age` pins the first; the hand audit is the answer to the second.

## What this means for a matcher

**Match on the structured fields.** They are present on 97% of trials, they are typed, and
nothing has to be parsed out of a sentence to use them. 13% of those trials are open to
under-18s, which is the kind of question the structured fields answer cleanly.

**Do not treat criteria prose as a source of typed constraints.** Not with patterns, and —
this is the part that matters for a 14B — not with a model asked the same badly-posed
question. "What is the minimum age?" has no answer for most of these trials. It has a
*list* of answers that depend on which cohort, which scale, and which person the sentence
is about. A model asked for a single number will produce one, and 90% of the time it will
be as wrong as the regex was.

The useful question for a model here is the one the audit had to answer by hand: *is this
age the trial's own entry requirement, or is it doing something else?* That is a
classification with a real answer, and the 48 labels are the start of a set to measure it
on.

## Layout

```
scripts/fetch_trials.py               ClinicalTrials.gov v2, paged, no key
src/trialmatch/corpus.py              12,500 trials; structured + prose age parsing
scripts/measure.py                    every table above
data/age_disagreement_labels.json     48 hand labels, each with its evidence
tests/                                28 tests, incl. the label file vs the corpus
```
