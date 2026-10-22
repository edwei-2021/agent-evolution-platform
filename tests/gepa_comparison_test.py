"""Paired release rules and complete, independently sourced final-task identity."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from gepa_comparison import POLICY, paired_final, release_blockers


def evidence():
    data = {s: [{'id': s+str(i), 'group': 'group-'+str(i), 'difficulty': 'hard', 'topic': 'ordering'}
                for i in range(4)] for s in ('validation', 'heldout')}
    ledger = []
    for split, tasks in data.items():
        for label, scores in (('baseline', [0, 1, 1, 0]), ('selected', [1, 0, 1, 0])):
            for task, score in zip(tasks, scores):
                ledger.append({'id': f'R{len(ledger)+1:04d}', 'stage': label, 'taskId': task['id'], 'score': score})
    return data, ledger


class GepaComparisonTests(unittest.TestCase):
    def test_all_four_outcomes_match_final_identity_and_ignore_search(self):
        data, ledger = evidence()
        report = paired_final(data, [{'stage': 'search', 'score': 1}]+ledger)
        self.assertEqual(len(report['tasks']), 8)
        for split in data:
            self.assertEqual(report['splits'][split],
                             {'improved': 1, 'regressed': 1, 'retained-pass': 1, 'retained-fail': 1})
        self.assertEqual(report['tasks'][0]['baselineRolloutId'], 'R0001')
        self.assertEqual(report['tasks'][0]['selectedRolloutId'], 'R0005')
        self.assertNotIn('source', str(report))

    def test_missing_duplicate_cross_split_and_nonbinary_rows_fail_closed(self):
        data, rows = evidence()
        variants = [rows[:-1], rows+[rows[0]], [dict(r, score=True) if i == 0 else r for i,r in enumerate(rows)],
                    [dict(r, taskId='unknown') if i == 0 else r for i,r in enumerate(rows)],
                    [dict(r, stage='other') if i == 0 else r for i,r in enumerate(rows)],
                    [dict(r, id=rows[0]['id']) if i == 1 else r for i,r in enumerate(rows)]]
        for ledger in variants:
            with self.subTest(ledger=ledger[:1]), self.assertRaises(ValueError):
                paired_final(data, ledger)
        duplicate = copy.deepcopy(data)
        duplicate['heldout'][0]['id'] = duplicate['validation'][0]['id']
        with self.assertRaises(ValueError):
            paired_final(duplicate, rows)

    def test_net_gain_cannot_hide_regression_in_either_split(self):
        data, rows = evidence()
        # Turn the shared failure into another selected success: net +1, still one loss.
        for r in rows:
            if r['stage'] == 'selected' and r['taskId'].endswith('3'):
                r['score'] = 1
        report = paired_final(data, rows)
        final = {label: {s: {'passed': p, 'total': 4} for s in data}
                 for label,p in (('baseline', 2), ('selected', 3))}
        a,b = {'hash': 'baseline'}, {'hash': 'selected'}
        self.assertEqual(release_blockers(POLICY,a,b,final,report),
                         ['validation-task-regressed', 'heldout-task-regressed'])
        # Historical results use their recorded aggregate rule, not a fabricated new gate.
        self.assertEqual(release_blockers(None,a,b,final), [])
        for split in data:
            safe = copy.deepcopy(report)
            safe['splits'][split]['regressed'] = 0
            self.assertEqual(len(release_blockers(POLICY,a,b,final,safe)), 1)

    def test_positive_unchanged_tie_and_aggregate_loss_keep_all_existing_gates(self):
        data, rows = evidence()
        for row in rows:
            row['score'] = int(row['stage'] == 'selected')
        report = paired_final(data, rows)
        final = {label: {s: {'passed': p, 'total': 4} for s in data}
                 for label,p in (('baseline', 0), ('selected', 4))}
        a,b = {'hash': 'baseline'}, {'hash': 'selected'}
        self.assertEqual(release_blockers(POLICY,a,b,final,report), [])
        self.assertEqual(release_blockers(POLICY,a,a,final,report), ['unchanged-skill'])
        final['selected']['validation']['passed'] = 0
        final['baseline']['heldout']['passed'] = 4
        final['selected']['heldout']['passed'] = 3
        self.assertEqual(release_blockers(None,a,b,final), ['validation-not-improved','heldout-total-regressed'])
        for policy, comparison in (('unknown',report), (POLICY,None), (POLICY,{})):
            with self.assertRaises(ValueError):
                release_blockers(policy,a,b,final,comparison)

    def test_three_independent_final_repetitions_reject_one_regression_and_identity_tampering(self):
        data, original = evidence()
        validation=[r for r in original if r['taskId'].startswith('validation')]
        heldout=[r for r in original if r['taskId'].startswith('heldout')]
        rows=copy.deepcopy(validation)
        for rep in range(3):
            for row in heldout:
                rows.append({**row,'id':f'R{len(rows)+1:04d}','repetition':rep,
                             'score':1 if row['stage']=='selected' else int(rep!=2)})
        report=paired_final(data,rows,3)
        self.assertEqual(report['repetitions'],3)
        self.assertEqual(report['splits']['heldout']['regressed'],0)
        self.assertEqual(report['uncertainty']['allRepetitionsPassed'],{'baseline':0,'selected':4})
        self.assertEqual(len(report['tasks']),16)
        for altered in (rows[:-1],rows+[rows[-1]],
                        [{**r,'repetition':True} if i==len(rows)-1 else r for i,r in enumerate(rows)],
                        [{**r,'repetition':3} if i==len(rows)-1 else r for i,r in enumerate(rows)]):
            with self.assertRaises(ValueError):paired_final(data,altered,3)
        # A single same-repetition baseline pass and selected failure blocks release.
        rows[-1]['score']=0
        rows[-5]['score']=1
        report=paired_final(data,rows,3)
        self.assertGreaterEqual(report['splits']['heldout']['regressed'],1)


if __name__ == '__main__':
    unittest.main()
