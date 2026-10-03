"""Pull real clinical trials from ClinicalTrials.gov.

The API is public, versioned and needs no key. What makes it worth building on
is the `eligibilityCriteria` field: free text, written by the trial's own
sponsors, in the form every trial actually uses — a bulleted inclusion list and
an exclusion list, full of ages, lab values, prior treatments and comorbidities.

That is the matching problem stated in the source's own words rather than one
invented for a benchmark.

    python scripts/fetch_trials.py                 # 50 pages x 250 = up to 12,500
    python scripts/fetch_trials.py --out D:/corpus # or set TRIALMATCH_DATA

The download is resumable and atomic. Each finished page is appended to
``trials.json.part`` together with the token for the next page; an interrupted
run picks up from the last complete page (``--fresh`` discards it). The final
``trials.json`` only appears, via rename, once every page is in.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trialmatch.corpus import DATA_ENV, data_dir  # noqa: E402

API = "https://clinicaltrials.gov/api/v2/studies"
DEFAULT_PAGES = 50   # x DEFAULT_SIZE = the 12,500 trials the README describes
DEFAULT_SIZE = 250
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


def read_partial(part: Path) -> tuple[list[dict], str | None, int]:
    """Trials, next-page token and page count from an interrupted run.

    A torn last line (the process died mid-write) is dropped, so that page is
    simply fetched again.
    """
    trials: list[dict] = []
    token: str | None = None
    pages = 0
    if not part.exists():
        return trials, token, pages
    for line in part.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            break
        trials.extend(record["trials"])
        token = record["next"]
        pages += 1
    return trials, token, pages


def fetch_page(token: str | None, size: int, retries: int = 4) -> dict:
    for attempt in range(retries + 1):
        try:
            return page(token, size)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt == retries:
                raise
            wait = 2 ** attempt * 2
            print(f"  network error ({exc}); retrying in {wait}s", flush=True)
            time.sleep(wait)
    raise AssertionError("unreachable")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pull recruiting interventional trials from ClinicalTrials.gov."
    )
    parser.add_argument("--pages", type=int, default=DEFAULT_PAGES, help="pages to fetch")
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE, help="per page, max 1000")
    parser.add_argument(
        "--out", type=Path, default=None,
        help=f"directory for trials.json (default: ${DATA_ENV} or <repo>/data)",
    )
    parser.add_argument("--fresh", action="store_true", help="ignore a partial download")
    args = parser.parse_args(argv)
    if args.pages < 1 or not 1 <= args.size <= 1000:
        parser.error("--pages must be >= 1 and --size between 1 and 1000")

    out_dir = args.out or data_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "trials.json"
    part = out_dir / "trials.json.part"
    if args.fresh and part.exists():
        part.unlink()

    trials, token, done = read_partial(part)
    if done:
        print(f"  resuming after page {done}: {len(trials):,} trials so far", flush=True)

    with part.open("a", encoding="utf-8") as sink:
        n = done
        while n < args.pages and (n == 0 or token):
            try:
                payload = fetch_page(token, args.size)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                print(f"\nfetch stopped at page {n + 1}: {exc}\n"
                      f"re-run the same command to resume from {part}", file=sys.stderr)
                return 1
            batch = [t for t in (flatten(s) for s in payload.get("studies", [])) if t]
            token = payload.get("nextPageToken")
            sink.write(json.dumps({"next": token, "trials": batch}) + "\n")
            sink.flush()
            trials.extend(batch)
            n += 1
            print(f"  page {n:>3}: {len(trials):,} trials with criteria", flush=True)
            if token and n < args.pages:
                time.sleep(0.4)   # the API asks for restraint; this is well inside it

    tmp = out_dir / "trials.json.tmp"
    tmp.write_text(json.dumps({"trials": trials}, indent=0), encoding="utf-8")
    os.replace(tmp, out)
    part.unlink()
    print(f"\n{len(trials):,} trials -> {out}  ({out.stat().st_size / 1_048_576:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
