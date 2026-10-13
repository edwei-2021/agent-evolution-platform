"""Regression for WSL smoke workload plus independent reviewer replay."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from gepa_validation_budget import smoke_budget


class GepaBudgetTests(unittest.TestCase):
    def test_observed_wsl_rate_covers_full_smoke_and_review(self):
        # Prior WSL evidence: 18 rollouts passed, but reviewer was terminated
        # near 279 seconds before it could finish its independent replay.
        budget=smoke_budget(1.6926176800043322)
        self.assertEqual(budget['finalEvaluations'],12)
        self.assertGreaterEqual(budget['reviewReplays'],18)
        self.assertGreaterEqual(budget['workflowSeconds'],340)
        self.assertLess(budget['workflowSeconds'],7200)

    def test_invalid_calibration_cannot_start_a_run(self):
        with self.assertRaises(ValueError):smoke_budget(float('nan'))


if __name__=='__main__':
    unittest.main()
