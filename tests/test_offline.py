"""Behaviour that must hold on a fresh clone with no corpus and no network."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

from trialmatch import corpus

ROOT = Path(__file__).resolve().parents[1]


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fetch = _script("fetch_trials")


def _study(nct: str, criteria: str = "Age >= 18 years") -> dict:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": nct},
            "eligibilityModule": {
                "eligibilityCriteria": criteria,
                "minimumAge": "18 Years",
                "sex": "ALL",
            },
        }
    }


def _write_corpus(directory: Path, rows: list[dict]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "trials.json").write_text(json.dumps({"trials": rows}), encoding="utf-8")


def _row(nct: str, min_age: str = "18 Years", max_age: str = "", sex: str = "ALL") -> dict:
    return {
        "nct_id": nct,
        "title": nct,
        "status": "RECRUITING",
        "criteria": "x",
        "min_age": min_age,
        "max_age": max_age,
        "sex": sex,
    }


# --- data directory override -------------------------------------------------


def test_env_var_overrides_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(corpus.DATA_ENV, str(tmp_path))
    assert corpus.trials_path() == tmp_path / "trials.json"
    assert not corpus.available()
    _write_corpus(tmp_path, [_row("NCT1")])
    assert corpus.available()
    assert [t.nct_id for t in corpus.load()] == ["NCT1"]


def test_missing_corpus_error_names_the_fix(tmp_path, monkeypatch):
    monkeypatch.setenv(corpus.DATA_ENV, str(tmp_path / "nowhere"))
    with pytest.raises(corpus.TrialsMissingError, match="fetch_trials.py"):
        corpus.load()


def test_malformed_corpus_is_a_clear_error(tmp_path):
    bad = tmp_path / "trials.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not a trial-match corpus"):
        corpus.load(bad)


# --- structured matching ------------------------------------------------------


def test_structurally_eligible_uses_both_bounds_and_sex(tmp_path):
    _write_corpus(
        tmp_path,
        [
            _row("NCT_ADULT", "18 Years"),
            _row("NCT_PAED", "6 Months", "17 Years"),
            _row("NCT_WOMEN", "18 Years", sex="FEMALE"),
            _row("NCT_OPEN", ""),
        ],
    )
    trials = corpus.load(tmp_path / "trials.json")
    ids = lambda age, sex="ALL": {t.nct_id for t in corpus.structurally_eligible(trials, age, sex)}  # noqa: E731
    assert ids(10) == {"NCT_PAED", "NCT_OPEN"}
    assert ids(40, "male") == {"NCT_ADULT", "NCT_OPEN"}
    assert ids(40, "FEMALE") == {"NCT_ADULT", "NCT_WOMEN", "NCT_OPEN"}


@pytest.mark.parametrize(
    "age,sex,exc",
    [
        ("40", "ALL", TypeError),
        (None, "ALL", TypeError),
        (True, "ALL", TypeError),
        (-1, "ALL", ValueError),
        (200, "ALL", ValueError),
        (40, "other", ValueError),
    ],
)
def test_structurally_eligible_rejects_bad_input(age, sex, exc):
    with pytest.raises(exc):
        corpus.structurally_eligible([], age, sex)


# --- fetch: resumable and atomic ---------------------------------------------


def _fake_api(pages: list[list[dict]], fail_at: int | None = None):
    calls = []

    def page(token, size):
        index = 0 if token is None else int(token)
        calls.append(index)
        if fail_at is not None and index == fail_at:
            raise urllib.error.URLError("simulated outage")
        nxt = str(index + 1) if index + 1 < len(pages) else None
        return {"studies": pages[index], "nextPageToken": nxt}

    return page, calls


def test_fetch_resumes_after_an_interruption(tmp_path, monkeypatch):
    pages = [[_study("NCT1"), _study("NCT2")], [_study("NCT3")], [_study("NCT4")]]
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    page, calls = _fake_api(pages, fail_at=2)
    monkeypatch.setattr(fetch, "page", page)

    assert fetch.main(["--out", str(tmp_path), "--pages", "5"]) == 1
    assert not (tmp_path / "trials.json").exists(), "no final file from a partial run"
    assert (tmp_path / "trials.json.part").exists()

    page, calls = _fake_api(pages)
    monkeypatch.setattr(fetch, "page", page)
    assert fetch.main(["--out", str(tmp_path), "--pages", "5"]) == 0
    assert calls == [2], "only the missing page is fetched again"
    rows = json.loads((tmp_path / "trials.json").read_text(encoding="utf-8"))["trials"]
    assert [r["nct_id"] for r in rows] == ["NCT1", "NCT2", "NCT3", "NCT4"]
    assert not (tmp_path / "trials.json.part").exists()


def test_fetch_drops_a_torn_last_line(tmp_path):
    part = tmp_path / "trials.json.part"
    part.write_text(
        json.dumps({"next": "1", "trials": [{"nct_id": "NCT1"}]}) + '\n{"next": ', encoding="utf-8"
    )
    trials, token, done = fetch.read_partial(part)
    assert (len(trials), token, done) == (1, "1", 1)


def test_fetch_skips_studies_without_criteria():
    assert fetch.flatten(_study("NCT1", criteria="  ")) is None


def test_default_fetch_can_reach_the_documented_corpus_size():
    """README says 12,500 trials; the old default of 40 pages x 250 capped at 10,000."""
    assert fetch.DEFAULT_PAGES * fetch.DEFAULT_SIZE >= 12_500


# --- documented commands on a fresh clone ------------------------------------


def _run(script: str, tmp_path: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, **{corpus.DATA_ENV: str(tmp_path), "PYTHONIOENCODING": "cp1252"})
    return subprocess.run(
        [sys.executable, str(ROOT / script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
    )


def test_demo_runs_without_the_corpus(tmp_path):
    result = _run("demo.py", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "5/48 are real" in result.stdout
    assert "fetch_trials.py" in result.stdout


def test_demo_runs_with_a_corpus(tmp_path):
    _write_corpus(tmp_path, [_row("NCT_PAED", "6 Months", "17 Years"), _row("NCT_ADULT")])
    result = _run("demo.py", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "1 of 2 recruiting trials admit" in result.stdout


def test_measure_without_corpus_exits_cleanly(tmp_path):
    result = _run("scripts/measure.py", tmp_path)
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert "fetch_trials.py" in result.stderr
