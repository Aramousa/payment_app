Offline dependency bundle

This project includes vendored Python packages for offline installs.

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

Windows offline install

```powershell
python -m pip install --no-index --find-links=vendor/wheels -r requirements.txt
```

Important
- `requirements.txt` is the current main stack and uses `Django 6`, which needs `Python >= 3.12`.
- `requirements-py310.txt` is the compatibility stack for Ubuntu 22.04 default Python `3.10`.
- The Linux bundles assume:
  - OS/arch: `x86_64`
  - glibc-compatible manylinux environment
- If the server uses a different architecture or Python version, a matching wheel bundle must be generated.
