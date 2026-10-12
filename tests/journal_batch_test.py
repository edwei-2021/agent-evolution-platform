"""Bounded journal transactions preserve records while reducing commit count."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from debug_log import DebugLog
from runtime_service import RuntimeService

class JournalBatchTests(unittest.TestCase):
    def test_batch_is_one_transaction_with_redaction_and_restart_visibility(self):
        with tempfile.TemporaryDirectory() as root:
            journal=DebugLog(root)
            journal.keep_open()
            try:
                rows=[{'module':'worker','level':'DEBUG','message':f'line {i} token=private-value'} for i in range(40)]
                with patch.object(journal,'connect',wraps=journal.connect) as calls:
                    self.assertTrue(journal.append_many(rows))
                    self.assertEqual(calls.call_count,1)
                records=DebugLog(root).list()['records']
                self.assertEqual(len(records),40)
                self.assertEqual(len({r['id'] for r in records}),40)
                self.assertTrue(all('private-value' not in r['message'] for r in records))
                with journal.connect() as db:
                    self.assertEqual(db.execute('PRAGMA synchronous').fetchone()[0],1)
            finally:
                journal.close()
            self.assertEqual(DebugLog(root).list()['retained'],40)

    def test_capture_chunks_batches_without_skipping_lines(self):
        with tempfile.TemporaryDirectory() as root:
            journal=DebugLog(root)
            service=RuntimeService.__new__(RuntimeService)
            service.logs=journal
            service.current={'id':'RUN-batch'}
            path=Path(root)/'worker.log'
            path.write_text(''.join(f'line {i}\n' for i in range(300)))
            with patch.object(journal,'append_many',wraps=journal.append_many) as batches:
                offset=service.capture_log({'role':'worker'},path,0)
                self.assertEqual(batches.call_count,3)
                self.assertTrue(all(len(c.args[0])<=128 for c in batches.call_args_list))
            self.assertEqual(offset,path.stat().st_size)
            self.assertEqual(journal.list(limit=500)['retained'],300)
            service.capture_log({'role':'worker'},path,offset)
            self.assertEqual(journal.list(limit=500)['retained'],300)

    def test_invalid_batch_cannot_partially_insert_and_retention_is_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            journal=DebugLog(root,retention=3)
            for rows in ([],[{'module':'worker','level':'INFO','message':'ok'},
                             {'module':'invalid','level':'INFO','message':'bad'}],
                         [{'module':'worker','level':'INFO','message':'x'}]*129):
                with self.assertRaises(ValueError):journal.append_many(rows)
            self.assertEqual(journal.list()['retained'],0)
            journal.append_many([{'module':'worker','level':'INFO','message':str(i)} for i in range(10)])
            self.assertEqual(journal.list()['retained'],3)
