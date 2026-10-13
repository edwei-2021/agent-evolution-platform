#!/usr/bin/env python3
"""Run only the first failing GEPA release case and retain its evidence."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid
from zipfile import ZipFile

from adaptive_validation import current
from check_steps import prompt_after_seconds, supervise
from gepa_validation_budget import smoke_budget
from repair_runtime import sdk_status


ROOT = Path(__file__).resolve().parents[1]
CASE = 'test_actual_js_client_to_python_api_dispatch_and_result_validation'


def main():
    sdk = sdk_status(ROOT)
    if not sdk['available']:
        print('GEPA_DIAG_BLOCKED pinned nanobot environment is unavailable', flush=True)
        return 78
    directory = ROOT/'.local/test-reports'/('GEPA-DIAG-'+uuid.uuid4().hex)
    directory.mkdir(parents=True)
    report_path = directory/'report.json'
    print(f'GEPA_DIAGNOSTIC_REPORT {report_path}', flush=True)
    print('STEP_STARTED filesystem-calibration expected_normal_seconds=10', flush=True)
    try:
        calibration = current()
        io_seconds = float(calibration['perCallIoAllowanceSeconds'])
        budget = smoke_budget(io_seconds)
        normal = budget['normalSeconds']
        prompt = prompt_after_seconds(normal)
        maximum = min(7200, max(budget['workflowSeconds'] + 60, prompt + 60))
        command = [sdk['python'], '-m', 'unittest', 'discover', '-s', 'tests',
                   '-p', 'gepa_test.py', '-k', CASE, '-v']
        report = {'schemaVersion': 1, 'case': CASE, 'startedAt': datetime.now(timezone.utc).isoformat(),
                  'status': 'running', 'calibration': calibration,
                  'workloadBudget': budget,
                  'normalSeconds': normal, 'promptAfterSeconds': prompt,
                  'maximumSeconds': maximum, 'command': command, 'log': 'test.log'}
        report_path.write_text(json.dumps(report, indent=2))
        print(f'STEP_COMPLETED filesystem-calibration per_call_io_seconds={io_seconds:.3f}', flush=True)
        print(f'STEP_STARTED {CASE}', flush=True)
        print(f'STEP_EXPECTED {CASE} normal_seconds={normal} '
              f'prompt_after_seconds={prompt} hard_limit_seconds={maximum}', flush=True)
        env = {**os.environ, 'AEP_TEST_REPORT_DIR': str(directory), 'PYTHONUNBUFFERED': '1'}
        with (directory/'test.log').open('w') as output:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, bufsize=1,
                                       start_new_session=True)
            observed = supervise(process, CASE, normal, maximum, interval=5,
                                 output_path=output, progress_interval=15)
        report.update(status='completed' if observed['exitCode'] == 0 else 'failed',
                      exitCode=observed['exitCode'], durationMs=observed['durationMs'],
                      overNormalSeconds=observed['overNormalSeconds'],
                      extensionApproved=observed['extensionApproved'],
                      finishedAt=datetime.now(timezone.utc).isoformat())
        evidence = directory/'failure-evidence/gepa_test'
        archives = []
        if evidence.is_dir():
            for support in sorted(evidence.iterdir()):
                if support.is_dir():
                    archive = shutil.make_archive(str(support), 'zip', root_dir=support)
                    archives.append(str(Path(archive)))
                    print(f'GEPA_DIAGNOSTIC_ARCHIVE {archive}', flush=True)
        report['supportArchives'] = archives
        report_path.write_text(json.dumps(report, indent=2))
        for archive in archives:
            # A single archive is sufficient for follow-up diagnosis, even if
            # separate report/log attachments fail during upload.
            with ZipFile(archive, 'a') as bundle:
                bundle.write(report_path, 'report.json')
                bundle.write(directory/'test.log', 'test.log')
        print(f'STEP_{report["status"].upper()} {CASE} {report["durationMs"]} ms', flush=True)
        print(f'GEPA_DIAGNOSTIC_REPORT {report_path}', flush=True)
        return 0 if report['status'] == 'completed' else 1
    except (OSError, ValueError, RuntimeError) as exc:
        report_path.write_text(json.dumps({'schemaVersion': 1, 'case': CASE, 'status': 'failed',
                                           'error': f'{type(exc).__name__}: {exc}'}, indent=2))
        print(f'GEPA_DIAG_FAILED {type(exc).__name__}: {exc}; report={report_path}', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
