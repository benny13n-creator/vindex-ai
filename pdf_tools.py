import ssl
import certifi

_original_create_default_context = ssl.create_default_context

def _fixed_create_default_context(*args, **kwargs):
    kwargs["cafile"] = certifi.where()
    return _original_create_default_context(*args, **kwargs)

ssl.create_default_context = _fixed_create_default_context
ssl._create_default_https_context = _fixed_create_default_context

