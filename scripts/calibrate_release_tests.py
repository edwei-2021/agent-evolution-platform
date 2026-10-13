#!/usr/bin/env python3
"""Measure local journal/file I/O used by first-run release-test estimates."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from adaptive_validation import current  # noqa: E402


def main():
    calibration = current()
    calibration['purpose'] = 'first-run release-test duration estimates; no model requests'
    print('RELEASE_TEST_CALIBRATION ' + json.dumps(calibration, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
