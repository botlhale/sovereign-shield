import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("wait_databricks_run", ROOT / "sh/wait_databricks_run.py")
waiter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(waiter)


def test_waiter_cancels_a_timed_out_run(monkeypatch):
    calls = []

    def timeout(*args, **kwargs):
        raise TimeoutError("synthetic timeout")

    jobs = SimpleNamespace(
        wait_get_run_job_terminated_or_skipped=timeout,
        cancel_run=lambda run_id: SimpleNamespace(result=lambda **kwargs: calls.append(run_id)),
    )
    monkeypatch.setattr(waiter, "WorkspaceClient", lambda **kwargs: SimpleNamespace(jobs=jobs))
    monkeypatch.setattr("sys.argv", ["wait_databricks_run.py", "--host", "https://example.test", "--run-id", "123"])
    with pytest.raises(RuntimeError, match="cancelled"):
        waiter.main()
    assert calls == [123]