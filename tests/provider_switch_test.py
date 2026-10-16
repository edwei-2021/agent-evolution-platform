"""Provider routing/authentication and shared workflow contracts; loopback only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from model_provider import STRATA_DEFAULTS, headers, payload
from ollama_bridge import OllamaBridge, DEFAULTS
from llm_transport import stream_chat

class Strata(BaseHTTPRequestHandler):
    calls = []
    mode = 'ok'
    def log_message(self, *args): pass
    def reply(self, data, code=200):
        raw=json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        self.calls.append((self.path, self.headers.get('Authorization'), None))
        if self.mode == 'redirect':
            self.send_response(302);self.send_header('Location','/credential-sink');self.end_headers();return
        if self.headers.get('Authorization') != 'Bearer fixture-secret':self.reply({'error':'unauthorized'},401);return
        if self.path == '/v1/models':self.reply({'data':[{'id':'fixture-model'}]})
        elif self.path == '/v1/status':self.reply({'service':'strata','engine':'fixture','model':'fixture-model','loaded':self.mode!='cold'})
        else:self.reply({'error':'unexpected native route'},404)
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.calls.append((self.path,self.headers.get('Authorization'),body))
        if self.headers.get('Authorization') != 'Bearer fixture-secret':self.reply({'error':'unauthorized'},401);return
        if self.mode == 'http-error':self.reply({'error':self.headers.get('Authorization')},503);return
        if self.path == '/v1/load':self.reply({'service':'strata','loaded':True,'model':'fixture-model'});return
        if self.path != '/v1/chat/completions':self.reply({'error':'unexpected route'},404);return
        if body.get('stream'):
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            row={'model':body['model'],'choices':[{'index':0,'delta':{'content':'OK'},'finish_reason':'stop'}]}
            self.wfile.write(('data: '+json.dumps(row)+'\n\ndata: [DONE]\n\n').encode())
        else:self.reply({'model':body['model'],'choices':[{'message':{'content':'OK'}}]})

class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'OPENAI_API_KEY':'fixture-secret'});self.env.start()
        Strata.calls=[];Strata.mode='ok';self.server=ThreadingHTTPServer(('127.0.0.1',0),Strata)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.config={**STRATA_DEFAULTS,'baseUrl':f'http://127.0.0.1:{self.server.server_port}/v1','model':'fixture-model','inferenceTimeout':10}
        self.bridge=OllamaBridge(self.temp.name);self.bridge.save(self.config,0)
    def tearDown(self):
        if self.bridge.warmup_thread:self.bridge.warmup_thread.join(15)
        self.server.shutdown();self.server.server_close();self.thread.join();self.env.stop();self.temp.cleanup()
    def test_profiles_restart_and_drafts_are_offline_and_keys_are_not_saved(self):
        old={**DEFAULTS,'host':'127.0.0.1','port':11435,'model':'fixture-ollama'}
        self.bridge.save(old,1);self.bridge.save(self.config,2)
        state=OllamaBridge(self.temp.name).snapshot()
        self.assertEqual(state['profiles']['ollama'],old);self.assertEqual(state['profiles']['strata'],self.config)
        self.assertEqual(state['kind'],'strata');self.assertEqual(state['openaiBaseUrl'],self.config['baseUrl'])
        self.assertEqual(Strata.calls,[])
        self.assertNotIn('fixture-secret',self.bridge.path.read_text())
        self.bridge.export_environment(Path(self.temp.name)/'client.env')
        self.assertNotIn('fixture-secret',(Path(self.temp.name)/'client.env').read_text())
    def test_metadata_chat_and_sse_send_only_strata_routes_with_frozen_auth(self):
        Strata.mode='cold';self.assertEqual(self.bridge.run('metadata',1)['status'],'METADATA_ONLY_PASS')
        self.assertEqual(self.bridge.run('chat',1,'OK')['status'],'INFERENCE_PASS')
        cfg=self.bridge.frozen()['config']
        reply,events=stream_chat(self.bridge.endpoint(cfg),cfg,payload(cfg,{'model':cfg['model'],'stream':True}),lambda _:None)
        self.assertEqual(reply['choices'][0]['message']['content'],'OK');self.assertTrue(events)
        self.assertEqual([x[0] for x in Strata.calls],['/v1/status','/v1/models','/v1/chat/completions','/v1/chat/completions'])
        self.assertTrue(all(x[1]=='Bearer fixture-secret' for x in Strata.calls))
        self.assertTrue(all(x[2]['reasoning_effort']=='none' for x in Strata.calls if x[2] is not None))
        with patch.dict(os.environ,{'OPENAI_API_KEY':'changed'}):
            with self.assertRaisesRegex(ValueError,'credentials changed'):headers(cfg)
        self.assertEqual(headers(DEFAULTS),{});self.assertNotIn('reasoning_effort',payload(DEFAULTS,{}))
    def test_missing_key_invalid_configs_busy_and_stale_revision_never_dispatch(self):
        for change in ({'baseUrl':'http://0.0.0.0:8081/v1'},{'baseUrl':'http://user:key@localhost:8081/v1'}, {'apiKeyEnv':'actual key'}, {'reasoningEffort':'unknown'},{'apiKey':'forbidden'}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.bridge.save({**self.config,**change},1)
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}):
            with self.assertRaisesRegex(ValueError,'environment variable'):self.bridge.frozen()
        with self.assertRaises(RuntimeError):self.bridge.save(self.config,0)
        self.bridge.operation.acquire()
        try:
            with self.assertRaises(RuntimeError):self.bridge.save(DEFAULTS,1)
        finally:self.bridge.operation.release()
        self.assertEqual(Strata.calls,[])
    def test_native_load_is_owned_and_never_calls_ollama_generate(self):
        self.bridge.start_warmup(1);self.bridge.warmup_thread.join(15)
        status=self.bridge.warmup_status();self.assertEqual(status['status'],'PRELOAD_PASS',status)
        self.assertFalse(self.bridge.operation.locked());self.assertEqual([c[0] for c in Strata.calls],['/v1/load'])
        self.assertEqual(Strata.calls[0][2],{})
    def test_http_failure_omits_echoed_secret_and_does_not_retry(self):
        Strata.mode='http-error';result=self.bridge.run('chat',1,'OK')
        self.assertEqual(result['status'],'FAIL');self.assertNotIn('fixture-secret',json.dumps(result));self.assertEqual(len(Strata.calls),1)
        for path in (Path(self.temp.name)/'.local').rglob('*.json*'):
            self.assertNotIn('fixture-secret',path.read_text())
    def test_run_freezing_resolves_the_endpoint_once(self):
        from runtime_service import RuntimeService
        service=RuntimeService(self.temp.name)
        try:
            service.ollama=self.bridge
            with patch.object(self.bridge,'endpoint',wraps=self.bridge.endpoint) as resolve:
                cfg=service.llm.freeze({'profile':'smoke','maxSeconds':60,'expectedRevision':1,'providerRevision':1})
            self.assertEqual(resolve.call_count,1);self.assertEqual(cfg['provider']['kind'],'strata')
            self.assertEqual(cfg['provider']['endpoint']+'/v1',self.config['baseUrl'])
            self.assertEqual(Strata.calls,[])
        finally:service.close()
    def test_redirect_is_not_followed_with_credentials(self):
        Strata.mode='redirect';self.assertEqual(self.bridge.run('metadata',1)['status'],'FAIL')
        self.assertEqual([c[0] for c in Strata.calls],['/v1/status'])
        with self.assertRaisesRegex(ValueError,'HTTP 302'):
            self.bridge.request(self.bridge.endpoint(self.config),'/v1/models',self.config)
        self.assertEqual([c[0] for c in Strata.calls],['/v1/status','/v1/models'])

if __name__=='__main__':unittest.main()
