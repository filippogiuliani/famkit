"""famkit: the code the family apps (weHub, doTrack, eaTrack, paTrack) share.

Each app includes this repository as a git submodule in backend/famkit and configures it once, at the end of its
db.py (every other module imports db first):

    import famkit
    famkit.configure('DOTRACK', 'doTrack', sys.modules[__name__])

From then on the shared modules read the app's environment variables with its prefix (DOTRACK_SMTP_HOST, …) and use
its database module (DATA_DIR, DB_PATH, transaction(), bump(), create_family()).

Modules: mail (SMTP), backup (SQLite copies with rotation), web (request helpers), hub (the link with weHub, for the
apps), oidc (sign-in with OpenID Connect providers, for the apps)."""
from . import config


def configure(prefix, name, db):
    """prefix: the apps' environment prefix ('DOTRACK'); name: shown to people and in User-Agent ('doTrack');
    db: the app's database module."""
    config.PREFIX, config.NAME, config.db = prefix.upper(), name, db
    from . import hub, mail
    mail.load()
    hub.load()
