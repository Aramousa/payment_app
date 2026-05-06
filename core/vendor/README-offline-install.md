Offline dependency bundle

This project includes vendored Python packages for offline installs.
Frontend static dependencies are also bundled in the repository under `static/css`, `static/js`, and `static/fonts`. The app does not need CDNs or online font downloads at runtime.

Offline upgrade rule
- Every application version must ship with all required Python wheels in `vendor/`.
- Do not run `pip install` against the internet on the target server.
- If `requirements.txt` or `requirements-py310.txt` changes, the matching wheel folder must be updated in the same release package.
- New frontend assets must be committed under `static/`; do not use CDN links.

Folders
- `vendor/wheels`: Windows / local development bundle
- `vendor/wheels-linux`: Linux bundle for `Python 3.13` with current `requirements.txt` (`Django 6`)
- `vendor/wheels-linux-py310-django52`: Linux bundle for `Python 3.10` with `requirements-py310.txt` (`Django 5.2`)

Deployment path 1: Ubuntu 22.04 with Python 3.12/3.13

Use the current app dependencies:

```bash
python3.13 -m pip install --no-index --find-links=vendor/wheels-linux -r requirements.txt
```

Deployment path 2: Ubuntu 22.04 default Python 3.10

Use the compatibility dependency set:

```bash
python3.10 -m pip install --no-index --find-links=vendor/wheels-linux-py310-django52 -r requirements-py310.txt
```

Collect local static files before starting the app:

```bash
python3.10 manage.py collectstatic --noinput
```

Windows offline install

```powershell
python -m pip install --no-index --find-links=vendor/wheels -r requirements.txt
```

Offline version upgrade

From the project root on the target server:

```bash
python3.13 -m pip install --no-index --find-links=vendor/wheels-linux -r requirements.txt
python3.13 manage.py migrate
python3.13 manage.py collectstatic --noinput
```

For Python `3.10` compatibility deployments:

```bash
python3.10 -m pip install --no-index --find-links=vendor/wheels-linux-py310-django52 -r requirements-py310.txt
python3.10 manage.py migrate
python3.10 manage.py collectstatic --noinput
```

For Windows local/offline deployments:

```powershell
python -m pip install --no-index --find-links=vendor/wheels -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Important
- `requirements.txt` is the current main stack and uses `Django 6`, which needs `Python >= 3.12`.
- `requirements-py310.txt` is the compatibility stack for Ubuntu 22.04 default Python `3.10`.
- The Persian font and frontend vendor assets are stored in the repository and served locally after `collectstatic`.
- `db.sqlite3`, `media/`, and generated `staticfiles/` are runtime artifacts and should not be deployed as source replacements.
- The Linux bundles assume:
  - OS/arch: `x86_64`
  - glibc-compatible manylinux environment
- If the server uses a different architecture or Python version, a matching wheel bundle must be generated.
