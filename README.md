# SmartNote Project Context

## Cấu trúc
- app.py — GUI customtkinter (4 tab: Scan, Lịch sử, Flashcard, Ôn tập)
- Paddle_ocr_scanner.py — OCR nhiều loại file
- summarizer.py — LSA + TextRank + KeyBERT + TextTeaser + Voting + Gemini
- database.py — SQLite: scans, summaries, keywords, flashcards, review_log (smartnote.db)
- textteaser_lib/ — TextTeaser Python port

## Stack
- PaddleOCR v3 (paddlepaddle 3.x)
- customtkinter, sumy, keybert, sentence-transformers
- SQLite (built-in)
- google-genai (Gemini 2.0 flash)

## Lưu ý quan trọng
- PaddleOCR v3: bỏ use_angle_cls, show_log, use_gpu → dùng device="cpu"
- Tắt PIR engine: config.disable_mkldnn() trong static_infer.py
- os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True" đặt đầu file
- TextTeaser đặt trong thư mục textteaser_lib/