import json
from pathlib import Path

from evaluation.benchmark_trial_validity import audit


def test_rejects_task_specific_solution_repository(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    trace.write_text(json.dumps({
        "type": "tool_call",
        "title": "execute",
        "content": "github search jpg-ocr-stat artifacts/skills/jpg-ocr-stat/solution",
    }) + "\n")
    report = audit(trace, "jpg-ocr-stat")
    assert not report["valid"]
    assert "remote-answer-discovery" in report["exclusion_reasons"]


def test_allows_generic_dependency_documentation(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    trace.write_text(json.dumps({
        "type": "tool_call",
        "title": "execute",
        "content": "curl https://openpyxl.readthedocs.io/en/stable/",
    }) + "\n")
    assert audit(trace, "xlsx-recover-data")["valid"]
