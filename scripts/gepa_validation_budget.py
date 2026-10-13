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
    # The reviewer independently replays every persisted rollout, including
    # trusted subprocess tests and journal writes. Reserve that complete pass
    # as well as the optimizer and final evaluator before the budget is frozen.
    normal = round(20 + typical * (3 + 6 * io_seconds))
    maximum = min(7200, max(150, round(60 + total * (7 + 5 * io_seconds))))
    return {'normalSeconds': min(normal, maximum), 'workflowSeconds': maximum,
            'searchEvaluations': 8, 'finalEvaluations': total - 8,
            'reviewReplays': total}
