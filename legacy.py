"""The names the apps had until 2026-11 (weHub, doTrack, paTrack, eaTrack): environment variables set with the old
names still work for a while, with a warning in the log, so a compose file can be updated after the new images.

  WEHUB_APP_DOTRACK_URL → WOMBAT_APP_KOOKA_URL, PATRACK_HUB_KEY → PELICAN_HUB_KEY, WEHUB_APPS=dotrack → kooka…

A variable already set with the new name always wins."""
import os
import re

NAMES = {'WEHUB': 'WOMBAT', 'DOTRACK': 'KOOKA', 'PATRACK': 'PELICAN', 'EATRACK': 'WALLABY'}
IDS = {k.lower(): v.lower() for k, v in NAMES.items()}
_done = False


def new_name(key):
    return '_'.join(NAMES.get(part, part) for part in key.split('_'))


def new_ids(value):
    """'dotrack,eatrack' → 'kooka,wallaby' (the list of apps in WOMBAT_APPS)."""
    return re.sub(r'[a-z]+', lambda m: IDS.get(m.group(0), m.group(0)), value)


def apply(environ=None):
    """Copy every old-named variable to its new name (once per process). Returns the old names found."""
    global _done
    env = os.environ if environ is None else environ
    if _done and environ is None:
        return []
    found = []
    for key in list(env):
        new = new_name(key)
        if new != key and new not in env:
            env[new] = new_ids(env[key]) if new.endswith('_APPS') else env[key]
            found.append(key)
    if found:
        print(f"[famkit] old variable names, rename them in the compose file: {', '.join(sorted(found))}", flush=True)
    if environ is None:
        _done = True
    return found
