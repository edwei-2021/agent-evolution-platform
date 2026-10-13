"""Bounded GEPA integration-test budgets from pre-dispatch storage calibration."""
import math
from gepa_dataset import dataset


def smoke_budget(io_seconds):
    if not math.isfinite(io_seconds) or io_seconds < 0:
        raise ValueError('Invalid GEPA storage calibration')
    rows = dataset('smoke')
    # Search is capped at eight metric evaluations; the final pass runs each
    # validation and heldout task for both frozen candidates, serially.
    total = 8 + 2 * (len(rows['validation']) + len(rows['heldout']))
    typical = 6 + 2 * (len(rows['validation']) + len(rows['heldout']))
    normal = round(15 + typical * (2 + 4 * io_seconds))
    maximum = min(7200, max(120, round(30 + total * (5 + 4 * io_seconds))))
    return {'normalSeconds': min(normal, maximum), 'workflowSeconds': maximum,
            'searchEvaluations': 8, 'finalEvaluations': total - 8}
