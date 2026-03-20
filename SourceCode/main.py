import os
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

from summarizer import summarize_file

    # ── Cấu hình ──────────────────────────────────────────
FILE_PATH     = r"G:\hoc code\TTCS\ThucTapCoSo\SourceCode\Screenshot 2026-03-20 200850.png"
GEMINI_KEY    = ""
NUM_SENTENCES = 3
    # ──────────────────────────────────────────────────────

if not os.path.exists(FILE_PATH):
        print(f"[!] Không tìm thấy file: {FILE_PATH}")
else:
        result = summarize_file(
            FILE_PATH,
            api_key=GEMINI_KEY,
            lang_ocr="en",
            num_sentences=NUM_SENTENCES,
            language="English",
        )

        print("\n" + "="*60)
        print("TEXTTEASER")
        print("="*60)
        print(result["textteaser"] or "(trống)")