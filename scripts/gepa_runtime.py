"""Optional GEPA package discovery in the pinned nanobot environment."""
if __package__:
    from .repair_runtime import sdk_status
    from .sdk_runtime_probe import package_status
else:
    from repair_runtime import sdk_status
    from sdk_runtime_probe import package_status

GEPA_VERSION = '0.1.4'


def inspect_gepa(python, sdk_available, *, cached_only=False):
    if not sdk_available:
        return {'available': False, 'version': None, 'requiredVersion': GEPA_VERSION,
                'errorCode': 'sdk_unavailable', 'error': 'Inspect nanobot SDK probe diagnostics first'}
    return package_status(python, 'gepa', 'gepa', GEPA_VERSION, cached_only=cached_only)


def gepa_status(root, sdk=None, *, cached_only=False):
    sdk = sdk_status(root, cached_only=cached_only) if sdk is None else sdk
    result = inspect_gepa(sdk['python'], sdk['available'], cached_only=cached_only)
    if not sdk['available']:
        result['sdk'] = sdk
    return result
