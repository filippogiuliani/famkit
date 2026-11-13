"""famkit on a minimal app: the service routes other apps reach through weHub, and ask()."""
import os
import sqlite3
import sys
import types
from contextlib import contextmanager

import pytest
import requests
from flask import Flask, g, jsonify

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import famkit  # noqa: E402
from famkit import backup, hub, web  # noqa: E402

KEY = 'k' * 40


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / 'test.db')
    conn = sqlite3.connect(path)
    conn.executescript('''
        CREATE TABLE families (id INTEGER PRIMARY KEY, name TEXT, hub_id INTEGER, hub_version INTEGER);
        CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, name TEXT, hub_id INTEGER, password_hash TEXT,
                            totp_secret TEXT);
        CREATE TABLE members (family_id INTEGER, user_id INTEGER, role TEXT, created_at TEXT DEFAULT (datetime('now')));
        INSERT INTO families VALUES (1, 'Rossi', 7, 1);
        INSERT INTO users VALUES (1, 'fil@x.it', 'Fil', 10, 'secret', 'totp'), (2, 'sara@x.it', 'Sara', 11, '!', NULL);
        INSERT INTO members (family_id, user_id, role) VALUES (1, 1, 'admin'), (1, 2, 'member');
    ''')
    conn.commit()
    conn.close()

    @contextmanager
    def transaction():
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    mod = types.SimpleNamespace(DATA_DIR=str(tmp_path), DB_PATH=path, transaction=transaction)
    monkeypatch.setenv('TESTAPP_HUB_URL', 'http://wehub.test')
    monkeypatch.setenv('TESTAPP_HUB_KEY', KEY)
    famkit.configure('TESTAPP', 'testApp', mod)
    return mod


@pytest.fixture
def client(db):
    app = Flask(__name__)
    app.register_blueprint(hub.bp, url_prefix='/api')
    return app.test_client()


@hub.service('/whoami')
def whoami():
    return jsonify(family_id=g.family_id, user=g.user, role=g.role, via_hub=g.via_hub)


@hub.service('/things/<int:thing_id>', methods=['PUT'])
def put_thing(thing_id):
    return jsonify(thing_id=thing_id, by=g.user['name']), 201


def test_service_needs_the_key(client):
    assert client.get('/api/hub/families/7/whoami?user=11').status_code == 401
    assert client.get('/api/hub/families/7/whoami?user=11', headers={'Authorization': 'Bearer nope'}).status_code == 401


def test_service_acts_as_the_member_who_asked(client):
    h = {'Authorization': 'Bearer ' + KEY}
    r = client.get('/api/hub/families/7/whoami?user=11', headers=h).get_json()
    assert r['family_id'] == 1 and r['user']['name'] == 'Sara' and r['role'] == 'member' and r['via_hub']
    # Someone who does not use this app: the family's first admin; private fields never in g.user
    r = client.get('/api/hub/families/7/whoami?user=99', headers=h).get_json()
    assert r['user']['name'] == 'Fil' and 'password_hash' not in r['user'] and 'totp_secret' not in r['user']
    assert client.get('/api/hub/families/8/whoami?user=11', headers=h).status_code == 404
    r = client.put('/api/hub/families/7/things/5?user=10', headers=h)
    assert r.status_code == 201 and r.get_json() == {'thing_id': 5, 'by': 'Fil'}


class Resp:
    def __init__(self, code, data):
        self.status_code, self._data = code, data

    def json(self):
        if self._data is None:
            raise ValueError()
        return self._data


def test_ask(db, monkeypatch):
    calls = []
    answer = [Resp(201, {'ok': True})]
    monkeypatch.setattr(requests, 'request', lambda *a, **kw: calls.append((a, kw)) or answer[0])
    assert hub.ask('dotrack', 'PUT', '/deadlines/patrack-3', 7, 10, {'title': 'x'}) == {'ok': True}
    (method, url), kw = calls[0]
    assert method == 'PUT' and url == 'http://wehub.test/api/service/apps/dotrack/families/7/deadlines/patrack-3'
    assert kw['params'] == {'user': 10} and kw['json'] == {'title': 'x'}
    assert kw['headers']['Authorization'] == 'Bearer ' + KEY and kw['headers']['User-Agent'] == 'testApp'
    answer[0] = Resp(403, {'error': 'This app may not ask that'})
    with pytest.raises(hub.AskError) as e:
        hub.ask('dotrack', 'GET', '/x', 7, 10)
    assert e.value.status == 403 and e.value.message == 'This app may not ask that'
    answer[0] = Resp(502, {'error': 'doTrack is not reachable'})
    with pytest.raises(hub.Unavailable) as e:
        hub.ask('dotrack', 'GET', '/x', 7, 10)
    assert not isinstance(e.value, hub.HubDown)
    answer[0] = Resp(500, None)
    with pytest.raises(hub.Unavailable):
        hub.ask('dotrack', 'GET', '/x', 7, 10)

    def down(*a, **kw):
        raise requests.ConnectionError('refused')
    monkeypatch.setattr(requests, 'request', down)
    with pytest.raises(hub.HubDown):
        hub.ask('dotrack', 'GET', '/x', 7, 10)


def test_env_prefix_and_backups(db, monkeypatch):
    assert hub.URL == 'http://wehub.test' and hub.enabled()
    monkeypatch.setenv('TESTAPP_BACKUP_KEEP', '2')
    names = set()
    for i in range(3):
        monkeypatch.setattr(backup.datetime, 'datetime', type('D', (backup.datetime.datetime,), {
            'now': classmethod(lambda cls, i=i: backup.datetime.datetime(2026, 1, 1, 0, 0, i))}))
        names.add(backup.create_backup('test'))
    assert len(names) == 3
    kept = sorted(b['name'] for b in backup.list_backups())
    assert kept == ['test-2026-01-01_000001.db', 'test-2026-01-01_000002.db']
    assert backup.backup_path('../x.db') is None and backup.backup_path(kept[0])


def test_web_helpers():
    assert web.text('  ciao  ', 3) == 'cia' and web.placeholders([1, 2, 3]) == '?,?,?'
