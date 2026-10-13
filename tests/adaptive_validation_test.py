"""Adaptive limits are calculated before dispatch and fail closed at the cap."""
from pathlib import Path
import sys
import json
import os
from unittest.mock import patch
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from adaptive_validation import calculate, calibrate, current, ENV

class AdaptiveValidationTests(unittest.TestCase):
    def test_budget_scales_with_workload_and_actual_storage_cost(self):
        fast = calculate([.001] * 5)
        slow = calculate([.2] * 5)
        self.assertGreater(slow['profiles']['full']['maxSeconds'], fast['profiles']['full']['maxSeconds'])
        self.assertGreater(fast['profiles']['full']['maxSeconds'], fast['profiles']['smoke']['maxSeconds'])
        self.assertEqual(slow['inferenceTimeout'], 10)
        self.assertEqual(slow['profiles']['full']['calls'], 101)
        self.assertEqual(slow['modelRequests'], 0)
    def test_invalid_or_excessive_cost_is_not_silently_clamped(self):
        for samples in [[], [-1], [float('nan')], [float('inf')], [100]]:
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                calculate(samples)
    def test_probe_stays_on_requested_filesystem_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as root:
            result = calibrate(root)
            self.assertEqual(result['filesystemRoot'], str(Path(root) / '.local/tmp'))
            self.assertEqual(len(result['samplesSeconds']), 5)
            self.assertEqual(list((Path(root) / '.local/tmp').iterdir()), [])

    def test_children_recompute_and_share_the_frozen_samples(self):
        value = calculate([.2] * 5)
        value['profiles']['full']['maxSeconds'] = 1
        current.cache_clear()
        try:
            with patch.dict(os.environ, {ENV: json.dumps(value)}):
                self.assertEqual(current()['profiles'], calculate([.2] * 5)['profiles'])
        finally:
            current.cache_clear()
