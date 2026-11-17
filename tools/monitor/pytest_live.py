from __future__ import annotations

import json
import os
import time

_path = os.environ.get("VXMON_FILE")
_started: dict[str, float] = {}


def _emit(**data) -> None:
    if not _path:
        return
    with open(_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def pytest_collection_finish(session):
    _emit(ev="total", n=len(session.items))


def pytest_runtest_logstart(nodeid, location):
    _started[nodeid] = time.perf_counter()
    _emit(ev="start", id=nodeid)


def pytest_runtest_logreport(report):
    if report.when == "call" or (report.outcome != "passed" and report.when in ("setup", "teardown")):
        outcome = report.outcome
        if report.when != "call" and outcome == "failed":
            outcome = "error"
        text = ""
        if outcome in ("failed", "error"):
            text = str(report.longreprtext)[-4000:]
        elif outcome == "skipped" and isinstance(report.longrepr, tuple):
            text = str(report.longrepr[2])
        _emit(ev="done", id=report.nodeid, outcome=outcome, text=text,
              seconds=round(time.perf_counter() - _started.get(report.nodeid, time.perf_counter()), 2))


def pytest_sessionfinish(session, exitstatus):
    _emit(ev="end", exit=int(exitstatus))
