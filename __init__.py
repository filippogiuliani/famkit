"""famkit: the code the family apps (Wombat, Kooka, Wallaby, Pelican) share.

Each app includes this repository as a git submodule in backend/famkit and configures it once, at the end of its
db.py (every other module imports db first):

    import famkit
    famkit.configure('KOOKA', 'Kooka', sys.modules[__name__])

From then on the shared modules read the app's environment variables with its prefix (KOOKA_SMTP_HOST, …) and use
its database module (DATA_DIR, DB_PATH, transaction(), bump(), create_family()).

Modules: mail (SMTP), backup (SQLite copies with rotation), web (request helpers), hub (the link with Wombat, for the
apps), oidc (sign-in with OpenID Connect providers, for the apps)."""
from . import legacy
legacy.apply()   # old environment names (weHub, doTrack…) still work for a while: see legacy.py

from . import config


def configure(prefix, name, db):
    """prefix: the apps' environment prefix ('KOOKA'); name: shown to people and in User-Agent ('Kooka');
    db: the app's database module."""
    config.PREFIX, config.NAME, config.db = prefix.upper(), name, db
    from . import hub, mail
    mail.load()
    hub.load()
