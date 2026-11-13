"""What famkit.configure() was told by the app."""
import os

PREFIX = ''   # 'DOTRACK'
NAME = ''     # 'doTrack'
db = None     # the app's db module


def env(key, default=''):
    """The app's environment variable {PREFIX}_{key}."""
    if not PREFIX:
        raise RuntimeError('famkit.configure() was not called')
    return os.environ.get(f'{PREFIX}_{key}', default)


def app_id():
    """'dotrack': how weHub calls this app."""
    return PREFIX.lower()
