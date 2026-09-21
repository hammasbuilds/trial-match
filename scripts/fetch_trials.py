"""Pull real clinical trials from ClinicalTrials.gov.

The API is public, versioned and needs no key. What makes it worth building on
is the `eligibilityCriteria` field: free text, written by the trial's own
sponsors, in the form every trial actually uses — a bulleted inclusion list and
an exclusion list, full of ages, lab values, prior treatments and comorbidities.

That is the matching problem stated in the source's own words rather than one
invented for a benchmark.

    python scripts/fetch_trials.py --pages 40
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://clinicaltrials.gov/api/v2/studies"
DATA = Path(__file__).resolve().parents[1] / "data"
OUT = DATA / "trials.json"

FIELDS = [
    "NCTId",
    "BriefTitle",
    "OverallStatus",
    "Phase",
    "Condition",
    "EligibilityCriteria",
    "MinimumAge",
    "MaximumAge",
    "Sex",
    "HealthyVolunteers",
    "StudyType",
    "EnrollmentCount",
    "LocationCountry",
]

# Recruiting interventional trials only. A completed trial cannot be matched to
# a patient, and an observational study asks a different question of the
# criteria, so mixing them in would measure two things at once.
QUERY = "AREA[OverallStatus]RECRUITING AND AREA[StudyType]INTERVENTIONAL"


def page(token: str | None, size: int) -> dict:
    params = {
        "pageSize": str(size),
        "fields": "|".join(FIELDS),
        "filter.advanced": QUERY,
    }
    if token:
        params["pageToken"] = token
    url = f"{API}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read())


def flatten(study: dict) -> dict | None:
    section = study.get("protocolSection", {})
    ident = section.get("identificationModule", {})
    elig = section.get("eligibilityModule", {})
    criteria = (elig.get("eligibilityCriteria") or "").strip()
    if not criteria:
        return None
    design = section.get("designModule", {})
    return {
        "nct_id": ident.get("nctId", ""),
        "title": ident.get("briefTitle", ""),
        "status": section.get("statusModule", {}).get("overallStatus", ""),
        "phases": design.get("phases", []),
        "enrollment": (design.get("enrollmentInfo") or {}).get("count"),
        "conditions": section.get("conditionsModule", {}).get("conditions", []),
        "criteria": criteria,
        "min_age": elig.get("minimumAge", ""),
        "max_age": elig.get("maximumAge", ""),
        "sex": elig.get("sex", ""),
        "healthy_volunteers": elig.get("healthyVolunteers"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=40)
    parser.add_argument("--size", type=int, default=250)
    args = parser.parse_args()

    DATA.mkdir(exist_ok=True)
    trials: list[dict] = []
    token = None

    for n in range(args.pages):
        payload = page(token, args.size)
        batch = [flatten(s) for s in payload.get("studies", [])]
        trials.extend(t for t in batch if t)
        token = payload.get("nextPageToken")
        print(f"  page {n + 1:>3}: {len(trials):,} trials with criteria")
        if not token:
            break
        time.sleep(0.4)   # the API asks for restraint; this is well inside it

    OUT.write_text(json.dumps({"trials": trials}, indent=0), encoding="utf-8")
    print(f"\n{len(trials):,} trials -> {OUT}  ({OUT.stat().st_size / 1_048_576:.1f} MB)")


if __name__ == "__main__":
    main()
