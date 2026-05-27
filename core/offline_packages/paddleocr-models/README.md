Offline PaddleOCR models

Put local PaddleOCR inference models in these folders before deploying to an offline server:

- `det/`: text detection model
- `rec/`: text recognition model
- `cls/`: optional angle classification model

The application reads these paths from Django settings:

- `PADDLEOCR_MODEL_DIR`
- `PADDLEOCR_DET_MODEL_DIR`
- `PADDLEOCR_REC_MODEL_DIR`
- `PADDLEOCR_CLS_MODEL_DIR`

If the detection and recognition model folders are empty or missing, image OCR is skipped with a clear warning instead of trying to download models from the internet.
