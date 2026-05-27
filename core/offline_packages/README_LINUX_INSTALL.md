# Offline install on Ubuntu 22.04

Run from the project root on the production server:

```bash
cd /var/www/visiunapp/core
source ../venv/bin/activate
bash offline_packages/install_offline_linux.sh
```

Manual command for Ubuntu 22.04 default Python 3.10:

```bash
pip install --no-index --find-links=vendor/wheels-linux-py310-django52 -r requirements.txt
```

Manual command for Python 3.12 or 3.13:

```bash
pip install --no-index --find-links=vendor/wheels-linux -r requirements.txt
```

OCR is optional and should be installed only on the OCR worker/server. The bundled `offline_packages/ocr-wheels` folder is Linux Python 3.12 oriented.

```bash
INCLUDE_OCR=1 bash offline_packages/install_offline_linux.sh
```

For Ubuntu 22.04 default Python 3.10, rebuild `offline_packages/ocr-wheels` for cp310 before enabling OCR.

PaddleOCR also needs local models:

```text
offline_packages/paddleocr-models/det
offline_packages/paddleocr-models/rec
offline_packages/paddleocr-models/cls
```

The application will not download OCR models from the internet at runtime.
