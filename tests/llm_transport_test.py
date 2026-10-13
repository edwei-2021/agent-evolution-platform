"""Protocol failure tests complement real loopback/subprocess LLM tests."""
import io
import json
from email.message import Message
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from llm_transport import StreamAccumulator, stream_chat

class Response(io.BytesIO):
    def __init__(self, data, content_type='text/event-stream'):
        super().__init__(data); self.headers = Message(); self.headers['Content-Type'] = content_type

class TransportTests(unittest.TestCase):
    def test_sse_comments_crlf_unicode_and_usage_are_reassembled(self):
        events = [{'model': 'mock:1', 'choices': [{'index': 0, 'delta': {'content': '{"output":"臺灣"}'}, 'finish_reason': 'stop'}]},
                  {'choices': [], 'usage': {'completion_tokens': 7}}]
        data = b': keepalive\r\n\r\n' + b''.join(('data: ' + json.dumps(e, ensure_ascii=False) + '\r\n\r\n').encode() for e in events) + b'data: [DONE]\r\n\r\n'
        updates = []
        with patch('llm_transport.urllib.request.build_opener') as factory:
            factory.return_value.open.return_value = Response(data)
            reply, recorded = stream_chat('http://127.0.0.1:1', {'inferenceTimeout': 10}, {'stream': True}, updates.append)
            factory.return_value.open.assert_called_once()
        self.assertEqual(reply['choices'][0]['message']['content'], '{"output":"臺灣"}')
        self.assertEqual(reply['usage']['completion_tokens'], 7)
        self.assertEqual(recorded, events); self.assertEqual(updates[-1]['chunks'], 2)

    def test_incomplete_malformed_and_oversized_streams_fail_without_resending(self):
        valid = {'choices': [{'delta': {'content': 'text'}}]}
        samples = [b'data: [DONE]\n\n', b'data: {bad}\n\n', b'data: ' + b'x' * 65536,
                   ('data: ' + json.dumps(valid) + '\n\n').encode(),
                   b'data: {"error":"model failed"}\n\n', b'\xff\n']
        for data in samples:
            with self.subTest(data=data[:40]), patch('llm_transport.urllib.request.build_opener') as factory:
                factory.return_value.open.return_value = Response(data)
                with self.assertRaises((ValueError, UnicodeError)):
                    stream_chat('http://127.0.0.1:1', {'inferenceTimeout': 10}, {'stream': True}, lambda _: None)
                factory.return_value.open.assert_called_once()

    def test_structured_json_fallback_consumes_the_same_response_once(self):
        data = {'choices': [{'message': {'content': '{"output":"ok"}'}}]}
        with patch('llm_transport.urllib.request.build_opener') as factory:
            factory.return_value.open.return_value = Response(json.dumps(data).encode(), 'application/json')
            reply, events = stream_chat('http://127.0.0.1:1', {'inferenceTimeout': 10}, {'stream': True}, lambda _: None)
            factory.return_value.open.assert_called_once()
        self.assertEqual(reply, data); self.assertIsNone(events)

    def test_stream_accumulator_bounds_and_rejects_invalid_delta_fields(self):
        for delta, finish in [({'content': 1}, 'stop'), ({'reasoning': []}, 'stop'), ({'content': 'x' * 12001}, 'stop'),
                              ({'reasoning_content': 'x' * 200001}, 'stop'), ({'content': 'ok'}, 1)]:
            with self.subTest(delta=str(delta)[:40]), self.assertRaises(ValueError):
                StreamAccumulator().add({'choices': [{'delta': delta, 'finish_reason': finish}]})


class AbsoluteDeadlineTests(unittest.TestCase):
    def test_continuous_chunks_do_not_reset_deadline(self):
        # Each read advances a controlled monotonic clock. No host filesystem
        # speed or real sleep participates in this deadline assertion.
        clock = [100.0]
        event = b'data: {"choices":[{"delta":{"content":"x"}}]}\n\n'
        class Trickle(Response):
            def readline(self, size=-1):
                clock[0] += .125
                return super().readline(size)
        updates = []
        response = Trickle(event * 20)
        with patch('llm_transport.time.monotonic', side_effect=lambda: clock[0]), \
             patch('llm_transport.urllib.request.build_opener') as factory:
            factory.return_value.open.return_value = response
            with self.assertRaisesRegex(TimeoutError, 'absolute time limit'):
                stream_chat('http://127.0.0.1:1', {'inferenceTimeout': 1}, {'stream': True}, updates.append)
            factory.return_value.open.assert_called_once()
            self.assertEqual(factory.return_value.open.call_args.kwargs['timeout'], 1)
        self.assertEqual(clock[0], 101.0)
        self.assertEqual(updates[-1]['chunks'], 4)

    def test_connection_time_consumes_the_same_absolute_deadline(self):
        clock = [100.0]
        def open_response(*args, **kwargs):
            clock[0] += 1
            return Response(b'data: [DONE]\n\n')
        with patch('llm_transport.time.monotonic', side_effect=lambda: clock[0]), \
             patch('llm_transport.urllib.request.build_opener') as factory:
            factory.return_value.open.side_effect = open_response
            with self.assertRaisesRegex(TimeoutError, 'absolute time limit'):
                stream_chat('http://127.0.0.1:1', {'inferenceTimeout': 1}, {'stream': True}, lambda _: None)
            factory.return_value.open.assert_called_once()
