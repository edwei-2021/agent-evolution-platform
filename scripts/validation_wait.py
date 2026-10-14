"""Bounded, observable first-request waits for loopback integration tests."""
import math
import time

TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}


def repair_workflow_seconds(io_seconds, call_budget=8):
    """Freeze the bounded repair test budget before SDK subprocess dispatch."""
    if (not math.isfinite(io_seconds) or io_seconds < 0 or type(call_budget) is not int
            or not 1 <= call_budget <= 12):
        raise ValueError('Invalid repair test calibration or call budget')
    seconds = max(90, math.ceil(40 + call_budget * (10 + 3 * io_seconds)))
    if seconds > 7200:
        raise ValueError('Repair test storage calibration exceeds the 7200-second limit')
    return seconds


def startup_budget(io_seconds, workflow_seconds):
    """Reserve process startup and journal writes without altering model deadlines."""
    if not math.isfinite(io_seconds) or io_seconds < 0 or workflow_seconds <= 0:
        raise ValueError('Invalid test startup calibration')
    return min(workflow_seconds, 180, max(30, math.ceil(20 + 30 * io_seconds)))


def first_request(event, service, run_id, seconds, *, label, interval=10):
    """Wait for the first mock request, reporting the actual current role."""
    if seconds <= 0 or interval <= 0:
        raise ValueError('Invalid test wait interval')
    start = time.monotonic()
    deadline = start + seconds
    next_report = start + min(interval, seconds)
    print(f'TEST_REQUEST_EXPECTED case={label} maximum_startup_seconds={seconds}', flush=True)
    while True:
        if event.is_set():
            print(f'TEST_REQUEST_RECEIVED case={label} elapsed_seconds={time.monotonic()-start:.1f}', flush=True)
            return
        now = time.monotonic()
        if now >= next_report or now >= deadline:
            run = service.get_run(run_id)
            role = next((a.get('role') for a in run.get('agents', ()) if a.get('status') == 'running'), 'queued')
            progress = run.get('gepaProgress') or run.get('repairProgress') or run.get('llmProgress') or {}
            print(f'TEST_REQUEST_WAIT case={label} elapsed_seconds={now-start:.1f} '
                  f'maximum_startup_seconds={seconds} status={run.get("status")} '
                  f'role={role} phase={progress.get("phase")} '
                  f'active_rollout={progress.get("activeRollout")}', flush=True)
            if event.is_set():
                return
            if run.get('status') in TERMINAL:
                raise AssertionError(f'{label}: workflow ended before the first mock request: '
                                     f'status={run.get("status")} error={run.get("error")}')
            next_report = now + interval
        if now >= deadline:
            raise AssertionError(f'{label}: first mock request not observed within {seconds}s; '
                                 'inspect TEST_REQUEST_WAIT and captured run evidence')
        event.wait(min(.25, deadline-now, max(.01, next_report-now)))
