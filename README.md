# famkit – shared code of the family apps

The code that **weHub**, **doTrack**, **eaTrack** and **paTrack** have in common, kept in one place instead of four
copies that drift apart. Each app includes this repository as a git submodule in `backend/famkit`:

```sh
git clone --recurse-submodules https://github.com/filippogiuliani/dotrack.git
# or, in a clone made without it:
git submodule update --init
# to move an app to a newer famkit:
cd backend/famkit && git pull && cd ../.. && git add backend/famkit && git commit -m "famkit: update"
```

The submodule points to a fixed commit: updating famkit never changes an app until that app is moved to the new
commit (and its tests pass).

## Modules

| Module | What | Used by |
|---|---|---|
| `famkit.configure(prefix, name, db)` | called once at the end of the app's `db.py` | all |
| `mail` | SMTP (`{PREFIX}_SMTP_*`), only logged when not configured | all |
| `backup` | SQLite copies with rotation in `<DATA_DIR>/backups` | all |
| `web` | `body()`, `text()`, `valid_date()`, `valid_time()`, `rows()`, `placeholders()` | all |
| `hub` | the link with weHub: sign-in, family copies, refresh, import/merge endpoints; apps asking each other | doTrack, eaTrack, paTrack |
| `oidc` | sign-in with OpenID Connect providers (Pocket ID, Google…) | doTrack, eaTrack, paTrack |

What differs between the apps stays in the app: `hub_hooks.py` (who the app's people are, what happens when a
member leaves, how families are merged), registered with `hub.use(hub_hooks)`, and `oidc.use(auth, tr, create_user)`.

## Apps asking each other

Always through weHub, which holds every app's key, checks that the person is in the family and may use the asking app
(and, for paTrack, the answering one too), and only passes on the calls listed in its `service.ALLOWED`.

```python
# the answering app (e.g. doTrack), in hub_hooks.py
@hub.service('/deadlines/<ref>', methods=['PUT'])
def put_deadline(ref):            # g.family_id, g.user, g.role are set; request.args['from'] is the asking app
    ...

# the asking app (e.g. paTrack)
hub.ask('dotrack', 'PUT', '/deadlines/patrack-12', family_hub_id, user_hub_id, {...})
```

`hub.ask` raises `AskError` (refused, with the reason), `HubDown` (weHub not reachable) or `Unavailable`.

## Tests

```sh
python -m pytest tests     # with Flask, requests and pytest installed (any app's .venv works)
```
