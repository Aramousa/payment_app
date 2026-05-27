Offline dependency bundle

This project includes vendored Python packages for offline installs.
Frontend static dependencies are also bundled in the repository under `static/css`, `static/js`, and `static/fonts`. The app does not need CDNs or online font downloads at runtime.
OCR-specific wheels and OCR engine files are stored under `offline_packages/`. PaddleOCR model files must be placed under `offline_packages/paddleocr-models` before deploying to a fully offline server.

Offline upgrade rule
- Every application version must ship with all required Python wheels in `vendor/`.
- Do not run `pip install` against the internet on the target server.
- If `requirements.txt` changes, the matching wheel folder must be updated in the same release package.
- New frontend assets must be committed under `static/`; do not use CDN links.
- OCR must not rely on first-run model downloads. Ship PaddleOCR detection and recognition models in the release package.
- The offline wheel bundle includes transitive runtime dependencies such as `typing_extensions`; keep these pinned in the requirements files so installation does not depend on online dependency resolution.
- Production server packages such as `gunicorn` and its dependency `packaging` are included in the wheel folders. The deployment package must include the complete `vendor/` directory, not only the Django source files.

Folders
- `vendor/wheels-linux`: Linux bundle for `Python 3.12/3.13` with `requirements.txt` (`Django 6` is selected by the Python version marker)
- `vendor/wheels-linux-py310-django52`: Linux bundle for Ubuntu 22.04 default `Python 3.10` with `requirements.txt` (`Django 5.2` is selected by the Python version marker)
- `offline_packages/ocr-wheels`: Optional Linux OCR wheel bundle. The current bundle is Python 3.12 oriented.

Deployment path 1: Ubuntu 22.04 with Python 3.12/3.13

Use the current app dependencies:

```bash
python3.13 -m pip install --no-index --find-links=vendor/wheels-linux -r requirements.txt
python3.13 -m gunicorn --version
```

Deployment path 2: Ubuntu 22.04 default Python 3.10

Use the compatibility dependency set:

```bash
python3.10 -m pip install --no-index --find-links=vendor/wheels-linux-py310-django52 -r requirements.txt
python3.10 -m gunicorn --version
```

Collect local static files before starting the app:

```bash
python3.10 manage.py collectstatic --noinput
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
python3.10 -m pip install --no-index --find-links=vendor/wheels-linux-py310-django52 -r requirements.txt
python3.10 manage.py migrate
python3.10 manage.py collectstatic --noinput
```

Important
- `requirements.txt` is the single dependency file. It uses Python version markers to install `Django 5.2.12` on Python `<3.12` and `Django 6.0.2` on Python `>=3.12`.
- The Persian font and frontend vendor assets are stored in the repository and served locally after `collectstatic`.
- `db.sqlite3`, `media/`, and generated `staticfiles/` are runtime artifacts and should not be deployed as source replacements.
- The Linux bundles assume:
  - OS/arch: `x86_64`
  - glibc-compatible manylinux environment
- If the server uses a different architecture or Python version, a matching wheel bundle must be generated.
- The production package is Linux-only for Ubuntu 22.04.
