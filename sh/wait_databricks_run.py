"""Wait for an existing run with visible state changes and a bounded timeout."""

import argparse
from datetime import timedelta

from databricks.sdk import WorkspaceClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--minutes", type=int, default=25)
    args = parser.parse_args()
    workspace = WorkspaceClient(host=args.host, auth_type="azure-cli")
    previous = None

    def report(run):
        nonlocal previous
        states = tuple((task.task_key, str(task.state.life_cycle_state), str(task.state.result_state)) for task in run.tasks or [])
        if states != previous:
            print(f"Run {args.run_id}: {run.state.life_cycle_state}", flush=True)
            for name, lifecycle, result in states:
                print(f"  {name}: {lifecycle} {result}", flush=True)
            previous = states

    try:
        run = workspace.jobs.wait_get_run_job_terminated_or_skipped(
            args.run_id, timeout=timedelta(minutes=args.minutes), callback=report,
        )
    except TimeoutError:
        workspace.jobs.cancel_run(args.run_id).result(timeout=timedelta(minutes=5))
        raise RuntimeError("The bounded test run timed out and was cancelled to limit compute use.")
    except Exception:
        run = workspace.jobs.get_run(args.run_id)
        report(run)
        for task in run.tasks or []:
            if str(task.state.result_state) == "RunResultState.FAILED":
                output = workspace.jobs.get_run_output(task.run_id)
                print(f"Failed task {task.task_key}: {output.error}", flush=True)
                print((output.error_trace or "")[:5000], flush=True)
        raise
    report(run)
    if str(run.state.result_state) != "RunResultState.SUCCESS":
        raise RuntimeError(f"Run ended without success: {run.state.result_state}")
    print("DATABRICKS_RUN_SUCCEEDED", flush=True)


if __name__ == "__main__":
    main()