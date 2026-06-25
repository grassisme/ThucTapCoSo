"""
Database - SQLite cho SmartNote
Lưu trữ: lịch sử scan, kết quả tóm tắt, flashcard
"""

import sqlite3
import os
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(__file__), "smartnote.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Tạo các bảng nếu chưa có."""
    conn = get_conn()
    c = conn.cursor()

    # ── Lịch sử scan ──────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name   TEXT NOT NULL,
            file_path   TEXT,
            file_type   TEXT,
            language    TEXT DEFAULT 'en',
            raw_text    TEXT,
            char_count  INTEGER DEFAULT 0,
            scanned_at  TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── Kết quả tóm tắt ───────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id     INTEGER NOT NULL,
            algorithm   TEXT NOT NULL,   -- lsa / textrank / keybert / voting / gemini ...
            content     TEXT NOT NULL,
            num_sentences INTEGER DEFAULT 3,
            created_at  TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (scan_id) REFERENCES scans(id) ON DELETE CASCADE
        )
    """)

    # ── Từ khoá KeyBERT ───────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS keywords (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id     INTEGER NOT NULL,
            keyword     TEXT NOT NULL,
            rank        INTEGER DEFAULT 0,
            FOREIGN KEY (scan_id) REFERENCES scans(id) ON DELETE CASCADE
        )
    """)

    # ── Flashcard ─────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS flashcards (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id     INTEGER,
            front       TEXT NOT NULL,   -- câu hỏi / từ khoá
            back        TEXT NOT NULL,   -- đáp án / định nghĩa
            hint        TEXT,            -- gợi ý (tuỳ chọn)
            deck        TEXT DEFAULT 'General',
            difficulty  INTEGER DEFAULT 0, -- 0=new, 1=easy, 2=medium, 3=hard
            next_review TEXT,              -- ngày ôn tập tiếp theo (spaced repetition)
            review_count INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (scan_id) REFERENCES scans(id) ON DELETE SET NULL
        )
    """)

    # ── Lịch sử ôn tập flashcard ──────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS review_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            flashcard_id INTEGER NOT NULL,
            result       TEXT NOT NULL,  -- 'correct' / 'wrong' / 'skip'
            reviewed_at  TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (flashcard_id) REFERENCES flashcards(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()
    print(f"[✓] Database sẵn sàng: {DB_PATH}")


# ── SCAN ──────────────────────────────────────────────────────────────────────

def save_scan(file_name, raw_text, file_path="", file_type="", language="en"):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO scans (file_name, file_path, file_type, language, raw_text, char_count)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (file_name, file_path, file_type, language, raw_text, len(raw_text)))
    scan_id = c.lastrowid
    conn.commit()
    conn.close()
    return scan_id


def get_all_scans():
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, file_name, file_type, language, char_count, scanned_at
        FROM scans ORDER BY scanned_at DESC
    """).fetchall()
    conn.close()
    return rows


def get_scan(scan_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM scans WHERE id=?", (scan_id,)).fetchone()
    conn.close()
    return row


def delete_scan(scan_id):
    conn = get_conn()
    conn.execute("DELETE FROM scans WHERE id=?", (scan_id,))
    conn.commit()
    conn.close()


# ── SUMMARY ───────────────────────────────────────────────────────────────────

def save_summary(scan_id, algorithm, content, num_sentences=3):
    conn = get_conn()
    conn.execute("""
        INSERT INTO summaries (scan_id, algorithm, content, num_sentences)
        VALUES (?, ?, ?, ?)
    """, (scan_id, algorithm, content, num_sentences))
    conn.commit()
    conn.close()


def save_summaries_bulk(scan_id, results: dict, num_sentences=3):
    """Lưu tất cả kết quả tóm tắt cùng lúc."""
    skip = {"raw_text", "cleaned_text", "error", "keywords"}
    conn = get_conn()
    for algo, content in results.items():
        if algo in skip or not content:
            continue
        conn.execute("""
            INSERT INTO summaries (scan_id, algorithm, content, num_sentences)
            VALUES (?, ?, ?, ?)
        """, (scan_id, algo, content, num_sentences))
    conn.commit()
    conn.close()


def get_summaries(scan_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT algorithm, content, num_sentences, created_at
        FROM summaries WHERE scan_id=?
        ORDER BY created_at
    """, (scan_id,)).fetchall()
    conn.close()
    return rows


# ── KEYWORDS ──────────────────────────────────────────────────────────────────

def save_keywords(scan_id, keywords: list):
    conn = get_conn()
    conn.execute("DELETE FROM keywords WHERE scan_id=?", (scan_id,))
    for i, kw in enumerate(keywords):
        conn.execute("INSERT INTO keywords (scan_id, keyword, rank) VALUES (?,?,?)",
                     (scan_id, kw, i))
    conn.commit()
    conn.close()


def get_keywords(scan_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT keyword FROM keywords WHERE scan_id=? ORDER BY rank
    """, (scan_id,)).fetchall()
    conn.close()
    return [r["keyword"] for r in rows]


# ── FLASHCARD ─────────────────────────────────────────────────────────────────

def add_flashcard(front, back, hint="", deck="General", scan_id=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO flashcards (scan_id, front, back, hint, deck)
        VALUES (?, ?, ?, ?, ?)
    """, (scan_id, front, back, hint, deck))
    fid = c.lastrowid
    conn.commit()
    conn.close()
    return fid


def auto_generate_flashcards(scan_id, results: dict, keywords: list):
    """
    Tự động sinh flashcard / câu hỏi từ kết quả scan:
      1. Rule-based QG: định nghĩa-trong-ngữ-cảnh + điền khuyết
         (summarizer.generate_questions) — đáp án thực, không còn để rỗng.
      2. Câu chủ đề mỗi đoạn (nếu có).
      3. (Tùy chọn) Transformer-based QG qua Gemini nếu đặt biến môi trường
         GEMINI_API_KEY — đúng nhánh "transformer-based" trong đề cương.
    """
    conn = get_conn()
    count = 0

    scan = get_scan(scan_id)
    deck = scan["file_name"] if scan else "Auto"
    raw_text = results.get("raw_text", "")

    def _add(front, back, hint=""):
        nonlocal count
        conn.execute(
            "INSERT INTO flashcards (scan_id, front, back, hint, deck) "
            "VALUES (?, ?, ?, ?, ?)",
            (scan_id, front, back, hint, deck))
        count += 1

    # 1) Rule-based QG (định nghĩa-trong-ngữ-cảnh + điền khuyết)
    try:
        from summarizer import generate_questions
        for q in generate_questions(raw_text, keywords[:12]):
            _add(q["front"], q["back"], q.get("hint", ""))
    except Exception as e:
        print(f"[!] QG rule-based lỗi: {e}")

    # 2) Câu chủ đề mỗi đoạn (nếu pipeline có cung cấp 'topics')
    topics = results.get("topics", "")
    if topics:
        bullets = [b.strip().lstrip("•").strip()
                   for b in topics.split("\n") if b.strip().startswith("•")]
        for i, bullet in enumerate(bullets):
            _add(f"Ý chính của đoạn {i+1} là gì?", bullet)

    # 3) (Tùy chọn) Transformer-based QG qua Gemini
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if api_key:
        try:
            from summarizer import generate_questions_ai
            for q in generate_questions_ai(raw_text, api_key):
                _add(q["front"], q["back"], q.get("hint", ""))
        except Exception as e:
            print(f"[!] QG AI lỗi: {e}")

    conn.commit()
    conn.close()
    return count


def get_flashcards(deck=None, due_only=False):
    """Lấy flashcard, có thể lọc theo deck hoặc chỉ lấy card đến hạn ôn."""
    conn = get_conn()
    if due_only:
        today = datetime.now().strftime("%Y-%m-%d")
        rows = conn.execute("""
            SELECT * FROM flashcards
            WHERE (next_review IS NULL OR next_review <= ?)
            AND deck = COALESCE(?, deck)
            ORDER BY difficulty ASC, review_count ASC
        """, (today, deck)).fetchall()
    elif deck:
        rows = conn.execute("""
            SELECT * FROM flashcards WHERE deck=?
            ORDER BY created_at DESC
        """, (deck,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM flashcards ORDER BY created_at DESC
        """).fetchall()
    conn.close()
    return rows


def get_decks():
    conn = get_conn()
    rows = conn.execute("""
        SELECT deck, COUNT(*) as count FROM flashcards GROUP BY deck
    """).fetchall()
    conn.close()
    return rows


def rename_deck(old_name: str, new_name: str) -> int:
    """Đổi tên bộ thẻ: cập nhật cột deck cho mọi flashcard thuộc bộ cũ.
    Trả về số thẻ đã cập nhật. Nếu new_name trùng một bộ đang có,
    các thẻ sẽ được gộp vào bộ đó (hành vi hợp lý, không mất dữ liệu)."""
    new_name = (new_name or "").strip()
    if not new_name or new_name == old_name:
        return 0
    conn = get_conn()
    cur = conn.execute(
        "UPDATE flashcards SET deck=? WHERE deck=?", (new_name, old_name))
    conn.commit()
    n = cur.rowcount
    conn.close()
    return n


def delete_deck(deck_name: str) -> int:
    """Xoá toàn bộ flashcard thuộc một bộ thẻ. Trả về số thẻ đã xoá."""
    conn = get_conn()
    cur = conn.execute("DELETE FROM flashcards WHERE deck=?", (deck_name,))
    conn.commit()
    n = cur.rowcount
    conn.close()
    return n


def update_flashcard(fid, front, back, hint="", deck="General"):
    conn = get_conn()
    conn.execute("""
        UPDATE flashcards SET front=?, back=?, hint=?, deck=?
        WHERE id=?
    """, (front, back, hint, deck, fid))
    conn.commit()
    conn.close()


def delete_flashcard(fid):
    conn = get_conn()
    conn.execute("DELETE FROM flashcards WHERE id=?", (fid,))
    conn.commit()
    conn.close()


def record_review(fid, result: str):
    """
    Ghi kết quả ôn tập và tính ngày ôn tiếp theo (Spaced Repetition đơn giản).
    result: 'correct' | 'wrong' | 'skip'
    """
    from datetime import timedelta

    conn = get_conn()

    # Lấy thông tin hiện tại
    card = conn.execute("SELECT * FROM flashcards WHERE id=?", (fid,)).fetchone()
    if not card:
        conn.close()
        return

    difficulty = card["difficulty"]
    review_count = card["review_count"] + 1

    # Tính ngày ôn tiếp theo
    if result == "correct":
        # Dễ hơn → khoảng cách dài hơn
        difficulty = min(difficulty + 1, 3)
        days_map = {0: 1, 1: 3, 2: 7, 3: 14}
    elif result == "wrong":
        # Khó → ôn lại sớm
        difficulty = max(difficulty - 1, 0)
        days_map = {0: 0, 1: 1, 2: 1, 3: 2}
    else:  # skip
        days_map = {0: 1, 1: 1, 2: 3, 3: 7}

    next_review = (datetime.now() + timedelta(days=days_map[difficulty])).strftime("%Y-%m-%d")

    conn.execute("""
        UPDATE flashcards
        SET difficulty=?, review_count=?, next_review=?
        WHERE id=?
    """, (difficulty, review_count, next_review, fid))

    conn.execute("""
        INSERT INTO review_log (flashcard_id, result) VALUES (?, ?)
    """, (fid, result))

    conn.commit()
    conn.close()


def get_stats():
    """Thống kê tổng quan."""
    conn = get_conn()
    stats = {}
    stats["total_scans"]     = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
    stats["total_summaries"] = conn.execute("SELECT COUNT(*) FROM summaries").fetchone()[0]
    stats["total_cards"]     = conn.execute("SELECT COUNT(*) FROM flashcards").fetchone()[0]
    stats["total_reviews"]   = conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0]
    stats["due_today"]       = conn.execute("""
        SELECT COUNT(*) FROM flashcards
        WHERE next_review IS NULL OR next_review <= date('now')
    """).fetchone()[0]
    conn.close()
    return stats


# ── Khởi tạo khi import ───────────────────────────────────────────────────────
init_db()
