"""Bounded OpenAI-compatible SSE transport, with no retries or proxy use."""
import json
import time
import urllib.error
import urllib.request


class StreamAccumulator:
    def __init__(self):
        self.events = []
        self.text = ''
        self.reasoning_chars = 0
        self.model = None
        self.usage = None
        self.finish = None

    def add(self, event):
        if not isinstance(event, dict) or event.get('error'):
            raise ValueError('Model stream error: ' + str(event.get('error') if isinstance(event, dict) else event))
        choices = event.get('choices')
        if not isinstance(choices, list) or len(choices) > 1:
            raise ValueError('Malformed model stream choices')
        if choices:
            choice = choices[0]
            if not isinstance(choice, dict) or choice.get('index', 0) != 0 or not isinstance(choice.get('delta'), dict):
                raise ValueError('Malformed model stream delta')
            delta = choice['delta']
            text = delta.get('content', '')
            reasoning = delta.get('reasoning_content', delta.get('reasoning', ''))
            if text is None: text = ''
            if reasoning is None: reasoning = ''
            if not isinstance(text, str) or not isinstance(reasoning, str):
                raise ValueError('Model stream text must be a string')
            self.text += text
            self.reasoning_chars += len(reasoning)
            if len(self.text) > 12000 or self.reasoning_chars > 200000:
                raise ValueError('Model stream output exceeds size limit')
            if choice.get('finish_reason') is not None:
                if not isinstance(choice['finish_reason'], str) or not choice['finish_reason']:
                    raise ValueError('Malformed model stream finish reason')
                self.finish = choice['finish_reason']
        self.model = event.get('model', self.model)
        if event.get('usage') is not None:
            self.usage = event['usage']
        self.events.append(event)
        if len(self.events) > 10000:
            raise ValueError('Model stream exceeds chunk limit')

    def summary(self):
        return {'chunks': len(self.events), 'outputChars': len(self.text),
                'reasoningChars': self.reasoning_chars, 'finishReason': self.finish}

    def reply(self):
        if self.finish is None:
            raise ValueError('Model stream ended without a finish reason')
        return {'model': self.model, 'choices': [{'message': {'content': self.text},
                'finish_reason': self.finish}], 'usage': self.usage}


def stream_chat(base, settings, payload, on_update):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(base + '/v1/chat/completions',
        data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json',
        'Accept': 'text/event-stream, application/json'})
    deadline = time.monotonic() + settings['inferenceTimeout']
    try:
        with opener.open(request, timeout=settings['inferenceTimeout']) as response:
            on_update({'responseStartedAt': time.time()})
            if response.headers.get_content_type() == 'application/json':
                # Some compatible servers ignore stream. Consume this one reply;
                # never resend the request or silently fall back to a second call.
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError('Model response exceeds 2 MB')
                if time.monotonic() >= deadline:
                    raise TimeoutError('Model call exceeded its absolute time limit')
                return json.loads(raw), None
            if response.headers.get_content_type() != 'text/event-stream':
                raise ValueError('Expected an SSE or JSON model response')
            accumulator = StreamAccumulator()
            size, event_lines = 0, []
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Model call exceeded its absolute time limit')
                line = response.readline(65537)
                size += len(line)
                if size > 2_000_000 or len(line) > 65536:
                    raise ValueError('Model stream exceeds size limit')
                if not line:
                    raise ValueError('Model stream disconnected before [DONE]')
                line = line.decode('utf-8').rstrip('\r\n')
                if line.startswith('data:'):
                    event_lines.append(line[5:].lstrip(' '))
                elif not line and event_lines:
                    data, event_lines = '\n'.join(event_lines), []
                    if data == '[DONE]':
                        return accumulator.reply(), accumulator.events
                    accumulator.add(json.loads(data))
                    on_update({**accumulator.summary(), 'lastChunkAt': time.time()})
    except urllib.error.HTTPError as exc:
        detail = exc.read(2048).decode(errors='replace')
        raise ValueError(f'Ollama HTTP {exc.code}: {detail}') from exc
