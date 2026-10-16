"""Provider-specific configuration and wire options; no network or stored keys."""
import hashlib
import ipaddress
import os
import re
import urllib.request
import urllib.error
from urllib.parse import urlsplit

STRATA_DEFAULTS = {'provider': 'strata', 'baseUrl': 'http://127.0.0.1:8081/v1',
    'model': '', 'apiKeyEnv': 'OPENAI_API_KEY', 'reasoningEffort': 'none',
    'metadataTimeout': 10, 'inferenceTimeout': 600, 'maxTokens': 256}


def kind(config):
    return config.get('provider', 'ollama')


def validate_strata(config):
    if set(config) != set(STRATA_DEFAULTS) or config['provider'] != 'strata':
        raise ValueError('Invalid Strata settings fields')
    base = config['baseUrl']
    if not isinstance(base, str):
        raise ValueError('Strata baseUrl must be an OpenAI base URL')
    base = base.rstrip('/')
    url = urlsplit(base)
    if (url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password
            or '?' in base or '#' in base or not url.path.endswith('/v1') or any(ord(c) < 33 for c in base)):
        raise ValueError('Use a Strata HTTP(S) base URL ending in /v1, without credentials/query/fragment')
    try:
        address = ipaddress.ip_address(url.hostname)
    except ValueError:
        name = url.hostname.encode('idna').decode('ascii').rstrip('.')
        if len(name) > 253 or any(not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', s) for s in name.split('.')):
            raise ValueError('Invalid Strata host')
    else:
        if address.is_unspecified or address.is_multicast:
            raise ValueError('Use a reachable Strata address, not a bind address')
    if url.port is not None and not 1 <= url.port <= 65535:
        raise ValueError('Invalid Strata port')
    for field, maximum in [('metadataTimeout', 120), ('inferenceTimeout', 3600), ('maxTokens', 8192)]:
        if type(config[field]) is not int or not 1 <= config[field] <= maximum:
            raise ValueError(f'{field} must be an integer in 1..{maximum}')
    if not isinstance(config['model'], str) or len(config['model']) > 200 or any(ord(c) < 32 for c in config['model']):
        raise ValueError('Invalid Strata model ID')
    if not isinstance(config['apiKeyEnv'], str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', config['apiKeyEnv']):
        raise ValueError('apiKeyEnv must name an environment variable, never contain a key')
    if config['reasoningEffort'] not in ('none', 'low', 'medium', 'high'):
        raise ValueError('Strata reasoningEffort must be none, low, medium or high')
    return {**config, 'baseUrl': base, 'model': config['model'].strip()}


def key(config):
    value = os.environ.get(config['apiKeyEnv'], '')
    if not value or any(ord(c) < 32 for c in value):
        raise ValueError('Strata key environment variable is missing or invalid: '+config['apiKeyEnv']+
                         '; start the GUI in the same prepared shell as ASK.py')
    expected = config.get('apiKeyDigest')
    if expected and expected != hashlib.sha256(value.encode()).hexdigest():
        raise ValueError('Strata credentials changed after configuration freezing')
    return value


def freeze(config):
    if kind(config) != 'strata':
        return dict(config)
    return {**config, 'apiKeyDigest': hashlib.sha256(key(config).encode()).hexdigest()}


def headers(config):
    return {'Authorization': 'Bearer '+key(config)} if kind(config) == 'strata' else {}


def payload(config, value):
    return {**value, 'reasoning_effort': config['reasoningEffort']} if kind(config) == 'strata' else value


def environment_defaults():
    value = dict(STRATA_DEFAULTS)
    if all(os.environ.get(n) for n in ('OPENAI_BASE_URL', 'STRATA_MODEL', 'OPENAI_API_KEY')):
        try:
            value = validate_strata({**value, 'baseUrl': os.environ['OPENAI_BASE_URL'], 'model': os.environ['STRATA_MODEL']})
        except ValueError:
            pass
    return value


class NoProviderRedirect(urllib.request.HTTPRedirectHandler):
    handler_order = 100
    def http_error_302(self, req, fp, code, msg, response_headers):
        raise urllib.error.HTTPError(req.full_url, code, "Provider redirect refused", response_headers, fp)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def protect_opener(opener, config):
    if kind(config) == 'strata':
        opener.add_handler(NoProviderRedirect())
    return opener
