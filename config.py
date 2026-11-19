"""What famkit.configure() was told by the app."""
import os

PREFIX = ''   # 'KOOKA'
NAME = ''     # 'Kooka'
db = None     # the app's db module


def env(key, default=''):
    """The app's environment variable {PREFIX}_{key}."""
    if not PREFIX:
        raise RuntimeError('famkit.configure() was not called')
    return os.environ.get(f'{PREFIX}_{key}', default)


def app_id():
    """'kooka': how Wombat calls this app."""
    return PREFIX.lower()
