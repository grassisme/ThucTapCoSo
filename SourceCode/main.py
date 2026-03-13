import os
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

from Paddle_ocr_scanner import PaddleOCRScanner

scanner = PaddleOCRScanner(lang="vi")

result = scanner._run_ocr(r"G:\hoc code\TTCS\test_page1.png")
print("TYPE:", type(result))
print("LEN:", len(result) if result else 0)

for i, item in enumerate(result or []):
    print(f"\n--- item {i} ---")
    print("type item:", type(item))
    if isinstance(item, dict):
        print("keys:", list(item.keys()))
        print("rec_texts:", item.get("rec_texts"))