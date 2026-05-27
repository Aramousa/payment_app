# Offline package sources

- Main Python wheels: prepared from `requirements.txt` for the supported Ubuntu/Linux Python versions.
- OCR Python wheels: prepared from `requirements-ocr.txt`; currently Linux Python 3.12 oriented.
- Tesseract language data:
  - `fas.traineddata`
  - `eng.traineddata`

Production rule:

- Keep the production package Linux-only for Ubuntu 22.04.
- Do not run `pip install` without `--no-index` on the offline server.
- If the server Python version changes, rebuild the matching Linux wheelhouse before deployment.
