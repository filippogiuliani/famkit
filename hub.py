"""weHub link: the family (members, roles, people, who may use this app) is defined in weHub.

Configuration (all optional; without them the app works on its own as before):
  {PREFIX}_HUB_URL          weHub's address as this server reaches it, e.g. http://wehub:3004
  {PREFIX}_HUB_KEY          shared key, the same as WEHUB_APP_{PREFIX}_KEY in weHub
  {PREFIX}_HUB_PUBLIC_URL   weHub's address for people (links), default {PREFIX}_HUB_URL
  {PREFIX}_HUB_SYNC_SECONDS how often families are refreshed (default 120)

When on:
- sign-in only through the OIDC provider (the same Pocket ID as weHub); after it weHub says who the person is and
  which families they may use this app in. Those families are copied here (members, roles, people).
- the family, its members and people are changed only in weHub: those endpoints answer 409 here.
- families are refreshed every couple of minutes; if weHub is down, people who already signed in go on working.
- weHub reads this app's families once (GET /api/hub/export) to import them, then this app adopts its own rows.

What differs between the apps (who "people" are, what happens when a member leaves, how data is merged) is in the
app's hub_hooks module, registered with use(hub_hooks):
  apply_people(conn, family_id, snapshot)       make the app's people match weHub's
  export_people(conn, family_id) -> [...]       the app's people, for weHub's import
  on_member_removed(conn, family_id, user_id)   tidy up what pointed to a member who left
  merge_data(conn, src, dst, report)            move a family's data into another (see merge())
  bump(conn, family_id)                         optional: something changed (default db.bump, when it exists)

Apps asking each other (paTrack → doTrack, eaTrack → doTrack…) always go through weHub, which holds every app's key
and checks that the person may use both apps in that family:
  ask('dotrack', 'POST', '/deadlines', family_hub_id, user_hub_id, payload)   in the asking app
  @service('/deadlines', methods=['POST'])                                     in the answering app"""
import functools
import hmac
import json
import threading
import time
import traceback

import requests
from flask import Blueprint, abort, g, jsonify, request

from . import config

URL = KEY = PUBLIC_URL = ''
INTERVAL = 120
TIMEOUT = 8
NO_PASSWORD = '!'
hooks = None

bp = Blueprint('hub', __name__)


def load():
    global URL, KEY, PUBLIC_URL, INTERVAL
    URL = config.env('HUB_URL').rstrip('/')
    KEY = config.env('HUB_KEY')
    PUBLIC_URL = config.env('HUB_PUBLIC_URL').rstrip('/')
    INTERVAL = int(config.env('HUB_SYNC_SECONDS', '120'))


def use(module):
    """Register the app's hooks (see the module docstring)."""
    global hooks
    hooks = module


def _bump(conn, family_id):
    if hasattr(hooks, 'bump'):
        hooks.bump(conn, family_id)
    elif hasattr(config.db, 'bump'):
        config.db.bump(conn, family_id)


def enabled():
    return bool(URL and KEY)


def guard():
    """For endpoints that change the family: in weHub mode they are not used here."""
    if enabled():
        abort(409, 'The family is managed in weHub')


def public_info(family_id=None, user_id=None):
    """For /api/me: weHub's address and, for a signed-in person, the family apps they may use (the app switcher):
    apps: [{id, name, url, current}], this app included. None without weHub."""
    if not enabled():
        return None
    info = {'url': PUBLIC_URL or URL, 'name': 'weHub', 'apps': []}
    if family_id and user_id:
        with config.db.transaction() as conn:
            ensure_schema(conn)
            f = conn.execute('SELECT hub_apps FROM families WHERE id = ?', (family_id,)).fetchone()
            u = conn.execute('SELECT hub_id FROM users WHERE id = ?', (user_id,)).fetchone()
        try:
            data = json.loads(f['hub_apps']) if f and f['hub_apps'] else {}
        except ValueError:
            data = {}
        mine = set(data.get('access', {}).get(str(u['hub_id'] if u else ''), []))
        info['apps'] = [{'id': a['id'], 'name': a['name'], 'url': a['url'], 'current': a['id'] == config.app_id()}
                        for a in data.get('apps', []) if a.get('url') and (a['id'] in mine or a['id'] == config.app_id())]
    return info


_schema_ready = None  # the database already checked


def ensure_schema(conn):
    """Columns famkit keeps in the app's own tables (added on first use, so no app migration is needed)."""
    global _schema_ready
    if _schema_ready == config.db.DB_PATH:
        return
    if 'hub_apps' not in {c[1] for c in conn.execute('PRAGMA table_info(families)')}:
        conn.execute('ALTER TABLE families ADD COLUMN hub_apps TEXT')  # apps of the family and who may use which (JSON)
    _schema_ready = config.db.DB_PATH


class Unavailable(Exception):
    pass


class NoAccess(Exception):
    pass


class HubDown(Unavailable):
    """weHub itself could not be reached (ask())."""


def _call(method, path, payload=None):
    try:
        r = requests.request(method, f'{URL}/api/service{path}', json=payload, timeout=TIMEOUT, allow_redirects=False,
                             headers={'Authorization': f'Bearer {KEY}', 'User-Agent': config.NAME})
    except requests.RequestException as e:
        raise Unavailable(f'{type(e).__name__}: {e}')
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise Unavailable(f'weHub answered {r.status_code}')
    return r.json()


def _key_ok():
    auth = request.headers.get('Authorization', '')
    presented = auth[7:].strip() if auth.startswith('Bearer ') else ''
    return bool(KEY) and hmac.compare_digest(KEY, presented)


# ---------- Sign-in ----------

def sign_in(provider, issuer, subject, email, email_verified, name):
    """The local user for someone who just signed in with the provider, their families updated from weHub.
    Raises NoAccess (not in a family that may use this app) or Unavailable (weHub down and never seen before)."""
    db = config.db
    try:
        who = _call('POST', '/whoami', {'issuer': issuer, 'subject': subject, 'email': email,
                                        'email_verified': bool(email_verified), 'name': name})
    except Unavailable:
        with db.transaction() as conn:
            u = conn.execute('''SELECT u.* FROM identities i JOIN users u ON u.id = i.user_id
                                WHERE i.provider = ? AND i.subject = ? AND u.hub_id IS NOT NULL''', (provider, subject)).fetchone()
            if u and conn.execute('SELECT 1 FROM members WHERE user_id = ?', (u['id'],)).fetchone():
                return u
        raise
    if not who or not who.get('known') or not who.get('families'):
        raise NoAccess()
    with db.transaction() as conn:
        uid = _user(conn, who['user'])
        keep = {apply_family(conn, snap) for snap in who['families']}
        for (fid,) in conn.execute('''SELECT m.family_id FROM members m JOIN families f ON f.id = m.family_id
                                      WHERE m.user_id = ? AND f.hub_id IS NOT NULL''', (uid,)).fetchall():
            if fid not in keep:
                _remove_member(conn, fid, uid)
        return conn.execute('SELECT * FROM users WHERE id = ?', (uid,)).fetchone()


def _user(conn, u):
    """Local user id for a weHub user (by weHub id, then by email), created when missing."""
    r = conn.execute('SELECT id FROM users WHERE hub_id = ?', (u['hub_id'],)).fetchone() or \
        conn.execute('SELECT id FROM users WHERE email = ? AND hub_id IS NULL', (u['email'],)).fetchone()
    if r:
        uid = r['id']
        conn.execute('UPDATE users SET hub_id = ?, name = ?, email_verified = 1 WHERE id = ?', (u['hub_id'], u['name'], uid))
        if not conn.execute('SELECT 1 FROM users WHERE email = ? AND id != ?', (u['email'], uid)).fetchone():
            conn.execute('UPDATE users SET email = ? WHERE id = ?', (u['email'], uid))
        return uid
    return conn.execute("INSERT INTO users (email, name, password_hash, email_verified, language, consent_at, hub_id) "
                        "VALUES (?,?,?,1,?,datetime('now'),?)",
                        (u['email'], u['name'], NO_PASSWORD, u.get('language') or 'it', u['hub_id'])).lastrowid


def _remove_member(conn, family_id, user_id):
    conn.execute('DELETE FROM members WHERE family_id = ? AND user_id = ?', (family_id, user_id))
    hooks.on_member_removed(conn, family_id, user_id)
    # Signed out everywhere: their next request finds no session
    if not conn.execute('SELECT 1 FROM members WHERE user_id = ?', (user_id,)).fetchone():
        conn.execute('UPDATE users SET session_version = session_version + 1 WHERE id = ?', (user_id,))


def apply_family(conn, snap):
    """Make the local copy of a weHub family match the snapshot. Returns the local family id."""
    f = conn.execute('SELECT id FROM families WHERE hub_id = ?', (snap['hub_id'],)).fetchone()
    if not f and snap.get('local_id'):
        f = conn.execute('SELECT id FROM families WHERE id = ? AND hub_id IS NULL', (snap['local_id'],)).fetchone()
    if f:
        fid = f['id']
        conn.execute('UPDATE families SET hub_id = ?, hub_version = ?, name = ? WHERE id = ?',
                     (snap['hub_id'], snap['version'], snap['name'], fid))
    else:
        lang = next((m.get('language') for m in snap['members'] if m.get('language')), 'it')
        fid = config.db.create_family(conn, snap['name'], lang)
        conn.execute('UPDATE families SET hub_id = ?, hub_version = ? WHERE id = ?', (snap['hub_id'], snap['version'], fid))
    wanted = {}
    for m in snap['members']:
        uid = _user(conn, m)
        wanted[uid] = m['role']
        conn.execute('INSERT INTO members (family_id, user_id, role) VALUES (?,?,?) '
                     'ON CONFLICT(family_id, user_id) DO UPDATE SET role = excluded.role', (fid, uid, m['role']))
    for (uid,) in conn.execute('SELECT user_id FROM members WHERE family_id = ?', (fid,)).fetchall():
        if uid not in wanted:
            _remove_member(conn, fid, uid)
    hooks.apply_people(conn, fid, snap)
    ensure_schema(conn)
    conn.execute('UPDATE families SET hub_apps = ? WHERE id = ?', (json.dumps({
        'apps': [{k: a.get(k) for k in ('id', 'name', 'url')} for a in snap.get('apps') or []],
        'access': {str(m['hub_id']): m.get('apps') or [] for m in snap['members']}}), fid))
    _bump(conn, fid)
    return fid


# ---------- Periodic refresh ----------

def sync_all():
    with config.db.transaction() as conn:
        fams = conn.execute('SELECT hub_id FROM families WHERE hub_id IS NOT NULL').fetchall()
    for f in fams:
        sync_family(f['hub_id'])


_sync_lock = threading.Lock()


def sync_family(hub_id):
    """Bring the local copy of one weHub family up to date. False when this app does not have that family."""
    with _sync_lock:  # the periodic refresh and a message from weHub must not apply the same family twice at once
        with config.db.transaction() as conn:
            ensure_schema(conn)
            f = conn.execute('SELECT hub_version, hub_apps FROM families WHERE hub_id = ?', (hub_id,)).fetchone()
        if not f:
            return False
        # Without the apps yet (copied by an older version): the whole snapshot, once
        version = f['hub_version'] if f['hub_apps'] and f['hub_version'] is not None else ''
        snap = _call('GET', f"/families/{hub_id}?version={version}")
        if snap is None:
            print(f'[hub] family {hub_id} no longer exists in weHub: local copy kept as it is', flush=True)
            return True
        if not snap.get('unchanged'):
            with config.db.transaction() as conn:
                apply_family(conn, snap)
        return True


@bp.post('/hub/changed')
def changed():
    """weHub: {family: weHub id} changed (members, roles, people, access). Refreshed now, not at the next round."""
    if not _key_ok():
        return jsonify(error='Unknown key'), 401
    try:
        hub_id = int((request.get_json(silent=True) or {}).get('family'))
    except (TypeError, ValueError):
        return jsonify(error='Invalid request'), 400
    try:
        known = sync_family(hub_id)
    except Unavailable as e:
        print(f'[hub] refresh after a change: {e}', flush=True)
        return jsonify(error='weHub not reachable'), 502
    return jsonify(ok=True, known=known)


def start_sync():
    if not enabled():
        return

    def loop():
        while True:
            time.sleep(INTERVAL)
            try:
                sync_all()
            except Unavailable as e:
                print(f'[hub] weHub not reachable: {e}', flush=True)
            except Exception:
                traceback.print_exc()

    threading.Thread(target=loop, daemon=True, name='hub-sync').start()
    print(f'[hub] family managed in weHub ({URL}), refreshed every {INTERVAL}s', flush=True)


# ---------- For weHub: what this app has (import) ----------

@bp.get('/hub/export')
def export():
    if not _key_ok():
        return jsonify(error='Unknown key'), 401
    out = []
    with config.db.transaction() as conn:
        for f in conn.execute('SELECT id, name, hub_id FROM families ORDER BY id').fetchall():
            members = [{'email': r['email'], 'name': r['name'], 'role': r['role']} for r in conn.execute(
                'SELECT u.email, u.name, m.role FROM members m JOIN users u ON u.id = m.user_id WHERE m.family_id = ?', (f['id'],))]
            out.append({'local_id': f['id'], 'name': f['name'], 'hub_id': f['hub_id'], 'members': members,
                        'people': hooks.export_people(conn, f['id'])})
    return jsonify(families=out)


# ---------- For weHub: merging families made separately before weHub ----------

@bp.post('/hub/merge')
def merge():
    """{into: local family id, families: [local family ids]}: move everything of those families into `into`.
    Called by weHub's import when two people had made separate families before. A backup of the database is made
    first; nothing is deleted except the emptied families (checked: if any row still belongs to one, nothing is done)."""
    if not _key_ok():
        return jsonify(error='Unknown key'), 401
    d = request.get_json(silent=True) or {}
    try:
        into = int(d.get('into'))
        sources = sorted({int(x) for x in d.get('families') or []} - {into})
    except (TypeError, ValueError):
        return jsonify(error='Invalid request'), 400
    if not sources:
        return jsonify(error='Nothing to merge'), 400
    with config.db.transaction() as conn:
        found = {r['id']: r for r in conn.execute(
            f"SELECT id, hub_id FROM families WHERE id IN ({','.join('?' * (len(sources) + 1))})", (into, *sources))}
        if into not in found or any(s not in found for s in sources):
            return jsonify(error='Family not found'), 404
        if any(found[s]['hub_id'] for s in sources):
            return jsonify(error='A family linked to weHub cannot be merged into another'), 409
    from . import backup
    backup.create_backup('pre-merge')
    report = {}
    try:
        with config.db.transaction() as conn:
            for src in sources:
                merge_family(conn, src, into, report)
            _bump(conn, into)
    except RuntimeError as e:
        print(f'[hub] merge cancelled: {e}', flush=True)
        return jsonify(error=str(e)), 409
    print(f'[hub] merged families {sources} into {into}: {report}', flush=True)
    return jsonify(merged=sources, into=into, report=report)


def merge_family(conn, src, dst, report):
    """Move one family into another inside the caller's transaction."""
    hooks.merge_data(conn, src, dst, report)
    # Members: everyone of both families stays (a role already held in the destination wins)
    for m in conn.execute('SELECT user_id, role FROM members WHERE family_id = ?', (src,)).fetchall():
        conn.execute('INSERT OR IGNORE INTO members (family_id, user_id, role) VALUES (?,?,?)', (dst, m['user_id'], m['role']))
    conn.execute('DELETE FROM members WHERE family_id = ?', (src,))
    conn.execute("DELETE FROM tokens WHERE family_id = ?", (src,))  # pending invitations of the old family
    # Safety net: no table may still hold rows of the old family, otherwise deleting it would cascade
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name != 'families'")]
    left = [t for t in tables if 'family_id' in {c[1] for c in conn.execute(f'PRAGMA table_info({t})')}
            and conn.execute(f'SELECT 1 FROM {t} WHERE family_id = ? LIMIT 1', (src,)).fetchone()]
    if left:
        raise RuntimeError(f'family {src} still has rows in {left}: merge cancelled')
    conn.execute('DELETE FROM families WHERE id = ?', (src,))
    report['families'] = report.get('families', 0) + 1


def count(report, key, n):
    """For merge_data: add n to report[key] (only when n > 0)."""
    if n:
        report[key] = report.get(key, 0) + n


# ---------- Apps asking each other, through weHub ----------

PRIVATE_USER_FIELDS = ('password_hash', 'totp_secret', 'totp_pending')


def service(rule, **options):
    """Route for requests another app makes through weHub: /api/hub/families/<weHub family id><rule>?user=<weHub id>.
    Checks this app's key, then sets g.family_id, g.user (the member who asked; when they do not use this app, the
    family's first admin), g.role, g.via_token = True, g.via_hub = True, like a normal signed-in request.
    The view gets the URL variables of `rule` (not the family id). Register with app.register_blueprint(hub.bp)."""
    def decorator(view):
        @functools.wraps(view)
        def wrapper(hub_family_id, **kwargs):
            if not _key_ok():
                return jsonify(error='Unknown key'), 401
            with config.db.transaction() as conn:
                f = conn.execute('SELECT id FROM families WHERE hub_id = ?', (hub_family_id,)).fetchone()
                if not f:
                    return jsonify(error=f'{config.NAME} does not know this family yet: sign in to {config.NAME} once'), 404
                u = conn.execute('''SELECT u.*, m.role AS member_role FROM members m JOIN users u ON u.id = m.user_id
                                    WHERE m.family_id = ?
                                    ORDER BY (u.hub_id IS ? AND u.hub_id IS NOT NULL) DESC, m.role = 'admin' DESC, m.created_at
                                    LIMIT 1''', (f['id'], request.args.get('user', type=int))).fetchone()
                if not u:
                    return jsonify(error=f'The family has no members in {config.NAME}'), 404
            u = {k: v for k, v in dict(u).items() if k not in PRIVATE_USER_FIELDS}
            g.role = u.pop('member_role')
            g.user, g.family_id, g.families, g.via_token, g.via_hub = u, f['id'], [], True, True
            return view(**kwargs)

        wrapper.__name__ = f'service_{view.__name__}'
        bp.add_url_rule(f'/hub/families/<int:hub_family_id>{rule}', endpoint=wrapper.__name__, view_func=wrapper, **options)
        return view
    return decorator


class AskError(Exception):
    """The other app (or weHub) said no: .status (HTTP) and .message, ready to show."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def ask(app_id, method, path, family_hub_id, user_hub_id, payload=None, timeout=10):
    """Ask another family app something through weHub. Returns its JSON answer; raises AskError (weHub or the other
    app refused: 400/403/404/409, with its message), HubDown (weHub cannot be reached) or Unavailable (the other app
    cannot be reached or answered with an error)."""
    if not enabled():
        raise Unavailable('weHub is not configured')
    try:
        r = requests.request(method, f'{URL}/api/service/apps/{app_id}/families/{family_hub_id}{path}',
                             params={'user': user_hub_id}, json=payload, timeout=timeout, allow_redirects=False,
                             headers={'Authorization': f'Bearer {KEY}', 'User-Agent': config.NAME})
    except requests.RequestException as e:
        raise HubDown(f'{type(e).__name__}: {e}')
    try:
        data = r.json()
    except ValueError:
        raise Unavailable(f'answer {r.status_code} is not JSON')
    if r.status_code in (200, 201):
        return data
    if r.status_code in (400, 403, 404, 409):
        raise AskError(r.status_code, (data or {}).get('error') or 'Refused')
    raise Unavailable((data or {}).get('error') or f'answered {r.status_code}')


def family_ids(conn, family_id):
    """(weHub family id, weHub user id of the current user) for asking another app, or None when not linked."""
    f = conn.execute('SELECT hub_id FROM families WHERE id = ?', (family_id,)).fetchone()
    u = conn.execute('SELECT hub_id FROM users WHERE id = ?', (g.user['id'],)).fetchone()
    if not f or not f['hub_id'] or not u or not u['hub_id']:
        return None
    return f['hub_id'], u['hub_id']
