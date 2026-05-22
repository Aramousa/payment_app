# Offline install on Ubuntu/Linux

Main install command on server:
cd /var/www/visiunapp/core
source ../venv/bin/activate
bash offline_packages/install_offline_linux.sh

Manual command:
pip install --no-index --find-links=offline_packages/python-wheels -r requirements.txt

OCR note:
requirements-ocr.txt is optional.
Do not use offline_packages/ocr-wheels unless it was built on Linux for the same Python version as the server.
For Ubuntu 22.04 with Python 3.12, OCR wheels must be Linux + Python 3.12 wheels.
Windows win_amd64 or Python cp313 wheels must not be used on production.
