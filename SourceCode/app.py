"""
SmartNote - Giao diện ứng dụng OCR + Tóm tắt + Flashcard
Dùng: python app.py
Cần cài: pip install customtkinter
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

try:
    import customtkinter as ctk
except ImportError:
    print("[!] Cần cài customtkinter: pip install customtkinter")
    sys.exit(1)

from database import (
    init_db, save_scan, save_summaries_bulk, save_keywords,
    auto_generate_flashcards, get_all_scans, get_scan, get_summaries,
    get_keywords, get_flashcards, get_decks, add_flashcard, update_flashcard,
    delete_flashcard, record_review, get_stats, delete_scan, rename_deck,
    delete_deck
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Design tokens ───────────────────────────────────────────────────────────
# Single-accent system: neutral zinc surfaces + one emerald accent.
# No "AI purple", no competing hues. Off-black base (never pure #000).
BG       = "#0a0a0d"   # app background (off-black, faint cool tint)
SURFACE  = "#121217"   # panels, headers
SUR2     = "#1a1a21"   # inputs, raised rows
BORDER   = "#272730"   # hairline separators
ACCENT   = "#2bb583"   # the one accent — deep emerald
ACCENT_H = "#239e72"   # accent pressed/hover (darker = tactile depth)
ACCENT2  = "#5fd3aa"   # lighter emerald — positive/result tint (same family)
ACCENT3  = "#cf9b52"   # restrained amber — functional only (difficulty)
TEXT     = "#ececf1"   # soft white
MUTED    = "#8b8b9a"   # muted, raised contrast for legibility
DANGER   = "#e8675f"   # desaturated red — semantic only
SUCCESS  = "#2bb583"   # = accent, keeps palette cohesive

# Typography: native Windows premium sans (no Inter, no serif on a dashboard)
FONT = "Segoe UI"
MONO = "Consolas"


# ══════════════════════════════════════════════════════════════════════════════
#  EXPORT HELPER
# ══════════════════════════════════════════════════════════════════════════════

def _export_txt(save_path: str, results: dict, file_name: str = "", scan_meta: dict = None):
    lines = []
    lines.append("=" * 60)
    lines.append("           SMARTNOTE — KẾT QUẢ XUẤT FILE")
    lines.append("=" * 60)
    if file_name:
        lines.append(f"File  : {file_name}")
    lines.append(f"Ngày  : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    if scan_meta:
        lines.append(f"Ngôn ngữ: {scan_meta.get('language','')}")
        lines.append(f"Độ dài  : {scan_meta.get('char_count','')} ký tự")
    lines.append("")

    section_map = [
        ("keywords",   "TỪ KHOÁ"),
        ("voting",     "TÓM TẮT (Voting Ensemble)"),
        ("lsa",        "TÓM TẮT (LSA)"),
        ("textrank",   "TÓM TẮT (TextRank)"),
        ("textteaser", "TÓM TẮT (TextTeaser)"),
        ("keybert",    "TÓM TẮT (KeyBERT)"),
        ("abstractive","TÓM TẮT (Gemini AI)"),
        ("topics",     "CÂU CHỦ ĐỀ"),
        ("raw_text",   "VĂN BẢN GỐC"),
    ]
    for key, title in section_map:
        val = results.get(key, "").strip()
        if not val:
            continue
        lines.append("-" * 60)
        lines.append(title)
        lines.append("-" * 60)
        lines.append(val)
        lines.append("")

    with open(save_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APP
# ══════════════════════════════════════════════════════════════════════════════

class SmartNoteApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SmartNote — OCR · Summary · Flashcard")
        self.geometry("1200x760")
        self.minsize(1000, 640)
        self.configure(fg_color=BG)

        self._build_header()
        self._build_nav()
        self._build_pages()
        self._show_page("scan")

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(hdr, text="Smart", font=(FONT,20,"bold"),
                     text_color=TEXT).pack(side="left", padx=(22,0))
        ctk.CTkLabel(hdr, text="Note", font=(FONT,20,"bold"),
                     text_color=ACCENT).pack(side="left")
        ctk.CTkLabel(hdr, text="   OCR · Summary · Flashcard",
                     font=(FONT,11), text_color=MUTED).pack(side="left")

        # Stats badge — mono digits, dot-separated, no emoji
        self.stats_lbl = ctk.CTkLabel(hdr, text="",
                                      font=(MONO,11), text_color=MUTED)
        self.stats_lbl.pack(side="right", padx=22)
        self._refresh_stats()

        # Hairline divider under header
        ctk.CTkFrame(self, fg_color=BORDER, height=1, corner_radius=0).pack(fill="x")

    def _refresh_stats(self):
        s = get_stats()
        self.stats_lbl.configure(
            text=f"{s['total_scans']} lượt scan   ·   "
                 f"{s['total_cards']} thẻ   ·   "
                 f"{s['due_today']} cần ôn"
        )

    # ── Nav sidebar ───────────────────────────────────────────────────────────
    def _build_nav(self):
        wrap = ctk.CTkFrame(self, fg_color=SURFACE, width=176, corner_radius=0)
        wrap.pack(side="left", fill="y")
        wrap.pack_propagate(False)
        self.nav = wrap

        ctk.CTkLabel(wrap, text="MENU", font=(FONT,10,"bold"),
                     text_color=MUTED).pack(anchor="w", padx=20, pady=(18,8))

        self.nav_btns = {}
        pages = [
            ("Scan",       "scan"),
            ("So sánh",    "compare"),
            ("Lịch sử",    "history"),
            ("Flashcard",  "flashcard"),
            ("Ôn tập",     "review"),
        ]
        for label, key in pages:
            btn = ctk.CTkButton(
                self.nav, text=label, anchor="w",
                fg_color="transparent", hover_color=SUR2,
                text_color=MUTED, font=(FONT,13),
                height=42, corner_radius=8,
                command=lambda k=key: self._show_page(k)
            )
            btn.pack(fill="x", padx=10, pady=2)
            self.nav_btns[key] = btn

        # Right hairline separating nav from content
        ctk.CTkFrame(self, fg_color=BORDER, width=1, corner_radius=0
                     ).pack(side="left", fill="y")

    def _show_page(self, key):
        for k, btn in self.nav_btns.items():
            if k == key:
                btn.configure(fg_color=SUR2, text_color=ACCENT, font=(FONT,13,"bold"))
            else:
                btn.configure(fg_color="transparent", text_color=MUTED, font=(FONT,13))
        for k, frame in self.pages.items():
            if k == key:
                frame.pack(side="left", fill="both", expand=True)
            else:
                frame.pack_forget()
        # Refresh khi chuyển trang
        if key == "history":   self._load_history()
        if key == "flashcard": self._load_flashcard_page()
        if key == "review":    self._load_review()

    # ── Pages container ───────────────────────────────────────────────────────
    def _build_pages(self):
        self.pages = {}
        for key in ["scan","compare","history","flashcard","review"]:
            frame = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
            self.pages[key] = frame

        self._build_scan_page(self.pages["scan"])
        self._build_compare_page(self.pages["compare"])
        self._build_history_page(self.pages["history"])
        self._build_flashcard_page(self.pages["flashcard"])
        self._build_review_page(self.pages["review"])


    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: SO SÁNH PHƯƠNG PHÁP TÓM TẮT
    # ══════════════════════════════════════════════════════════════════════════
    def _build_compare_page(self, parent):
        self.cmp_lang     = tk.StringVar(value="en")
        self.cmp_num_sent = tk.IntVar(value=3)
        self.cmp_source   = "scan"   # "scan" | "text"

        hdr = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=0, height=44)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="So sánh phương pháp tóm tắt",
                     font=(FONT,13,"bold"), text_color=TEXT).pack(side="left", padx=16)
        self.cmp_run_btn = ctk.CTkButton(
            hdr, text="Chạy so sánh", width=120, height=30,
            fg_color=ACCENT, hover_color=ACCENT_H, font=(FONT,12,"bold"),
            command=self._run_compare)
        self.cmp_run_btn.pack(side="right", padx=12)

        body = ctk.CTkFrame(parent, fg_color=BG)
        body.pack(fill="both", expand=True, padx=12, pady=8)

        cfg = ctk.CTkFrame(body, fg_color=SURFACE, corner_radius=12,
                           border_width=1, border_color=BORDER)
        cfg.pack(fill="x", pady=(0,8))

        # Hàng 1: nguồn đầu vào
        r1 = ctk.CTkFrame(cfg, fg_color="transparent")
        r1.pack(fill="x", padx=12, pady=(10,2))
        ctk.CTkLabel(r1, text="NGUỒN", font=(FONT,11,"bold"),
                     text_color=MUTED, width=70, anchor="w").pack(side="left")
        ctk.CTkSegmentedButton(
            r1, values=["Scan gần nhất","Dán văn bản"],
            font=(FONT,12), fg_color=SUR2, selected_color=ACCENT,
            selected_hover_color=ACCENT_H, unselected_color=SUR2,
            unselected_hover_color=BORDER, text_color=TEXT,
            command=self._on_cmp_source).pack(side="left")

        # Ô dán văn bản (ẩn mặc định, nằm ngay dưới hàng 1)
        self._cmp_text_holder = ctk.CTkFrame(cfg, fg_color="transparent")
        self._cmp_text_holder.pack(fill="x")
        self.cmp_text = ctk.CTkTextbox(
            self._cmp_text_holder, height=90, fg_color=SUR2, text_color=TEXT,
            font=(FONT,12), border_color=BORDER, border_width=1, wrap="word")

        # Hàng 2: ngôn ngữ + số câu
        r2 = ctk.CTkFrame(cfg, fg_color="transparent")
        r2.pack(fill="x", padx=12, pady=(6,2))
        ctk.CTkLabel(r2, text="NGÔN NGỮ", font=(FONT,11,"bold"),
                     text_color=MUTED, width=70, anchor="w").pack(side="left")
        for t, v in [("Tiếng Việt","vi"), ("English","en")]:
            ctk.CTkRadioButton(r2, text=t, variable=self.cmp_lang, value=v,
                               font=(FONT,12), text_color=TEXT, fg_color=ACCENT,
                               border_color=BORDER).pack(side="left", padx=(0,16))
        self.cmp_sent_lbl = ctk.CTkLabel(r2, text="3", font=(FONT,13,"bold"),
                                         text_color=ACCENT, width=24)
        self.cmp_sent_lbl.pack(side="right", padx=(6,0))
        ctk.CTkSlider(r2, from_=1, to=10, number_of_steps=9,
                      variable=self.cmp_num_sent, fg_color=BORDER,
                      progress_color=ACCENT, button_color=ACCENT,
                      button_hover_color=ACCENT_H, width=150,
                      command=lambda v: self.cmp_sent_lbl.configure(text=str(int(v)))
                      ).pack(side="right")
        ctk.CTkLabel(r2, text="Số câu", font=(FONT,11),
                     text_color=MUTED).pack(side="right", padx=(12,6))

        # Hàng 3: API key Gemini (tùy chọn)
        r3 = ctk.CTkFrame(cfg, fg_color="transparent")
        r3.pack(fill="x", padx=12, pady=(6,10))
        ctk.CTkLabel(r3, text="GEMINI", font=(FONT,11,"bold"),
                     text_color=MUTED, width=70, anchor="w").pack(side="left")
        self.cmp_api_key = ctk.CTkEntry(
            r3, placeholder_text="API key (tùy chọn — để có thêm cột abstractive)",
            fg_color=SUR2, border_color=BORDER, text_color=TEXT,
            font=(FONT,12), height=30)
        self.cmp_api_key.pack(side="left", fill="x", expand=True)

        # Khu kết quả
        self.cmp_results = ctk.CTkScrollableFrame(body, fg_color="transparent")
        self.cmp_results.pack(fill="both", expand=True)
        self._compare_empty_state()

    def _on_cmp_source(self, value):
        if value == "Dán văn bản":
            self.cmp_source = "text"
            self.cmp_text.pack(fill="x", padx=12, pady=(2,4))
            self.after(50, self.cmp_text.focus_set)
        else:
            self.cmp_source = "scan"
            self.cmp_text.pack_forget()

    def _compare_empty_state(self):
        for w in self.cmp_results.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.cmp_results,
            text="Chọn nguồn rồi nhấn \"Chạy so sánh\" để đối chiếu các phương pháp.\n"
                 "Chỉ số: tỉ lệ nén · số câu · thời gian chạy · độ phủ từ khoá.",
            font=(FONT,13), text_color=MUTED, justify="left"
            ).pack(anchor="w", padx=8, pady=20)

    def _compare_loading(self):
        for w in self.cmp_results.winfo_children():
            w.destroy()
        for _ in range(4):
            card = ctk.CTkFrame(self.cmp_results, fg_color=SURFACE, corner_radius=12,
                                border_width=1, border_color=BORDER, height=80)
            card.pack(fill="x", pady=4); card.pack_propagate(False)
            ctk.CTkFrame(card, fg_color=SUR2, corner_radius=6, height=14,
                         width=200).pack(anchor="w", padx=14, pady=(16,8))
            ctk.CTkFrame(card, fg_color=SUR2, corner_radius=6, height=10,
                         width=360).pack(anchor="w", padx=14)

    def _compare_error(self, msg):
        for w in self.cmp_results.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.cmp_results, text=f"Lỗi khi so sánh: {msg}",
                     font=(FONT,13), text_color=DANGER, justify="left",
                     wraplength=820).pack(anchor="w", padx=8, pady=20)

    def _run_compare(self):
        if self.cmp_source == "scan":
            text = (getattr(self, "scan_results", {}) or {}).get("raw_text", "").strip()
            if not text:
                messagebox.showinfo(
                    "Thông báo",
                    "Chưa có kết quả scan. Hãy scan ở tab Scan, hoặc chọn 'Dán văn bản'.")
                return
        else:
            text = self.cmp_text.get("1.0", "end").strip()
            if not text:
                messagebox.showinfo("Thông báo", "Hãy dán văn bản cần so sánh.")
                return
        self.cmp_run_btn.configure(state="disabled", text="Đang chạy…")
        self._compare_loading()
        threading.Thread(target=self._compare_worker, args=(text,), daemon=True).start()

    def _compare_worker(self, text):
        err, res = None, []
        try:
            from summarizer import compare_summaries
            res = compare_summaries(
                text, num_sentences=self.cmp_num_sent.get(),
                api_key=self.cmp_api_key.get().strip(),
                lang=self.cmp_lang.get())
        except Exception as e:
            err = str(e)

        def _done():
            self.cmp_run_btn.configure(state="normal", text="Chạy so sánh")
            if err:
                self._compare_error(err)
            else:
                self._render_compare(res)
        self.after(0, _done)

    def _render_compare(self, results):
        for w in self.cmp_results.winfo_children():
            w.destroy()
        if not results:
            self._compare_empty_state(); return

        ok = [r for r in results if not r["error"] and r["summary"].strip()]
        best_key = max(ok, key=lambda r: r["coverage"])["key"] if ok else None

        if ok:
            best = max(ok, key=lambda r: r["coverage"])
            ctk.CTkLabel(
                self.cmp_results,
                text=f"Phủ từ khoá cao nhất: {best['name']}  ({int(best['coverage'])}%)",
                font=(FONT,12,"bold"), text_color=ACCENT
                ).pack(anchor="w", padx=4, pady=(0,8))

        order = sorted(
            results,
            key=lambda r: (-(r["coverage"] if not r["error"] else -1), r["name"]))

        for r in order:
            is_best = r["key"] == best_key
            card = ctk.CTkFrame(self.cmp_results, fg_color=SURFACE, corner_radius=12,
                                border_width=2 if is_best else 1,
                                border_color=ACCENT if is_best else BORDER)
            card.pack(fill="x", pady=4)

            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=14, pady=(10,4))
            ctk.CTkLabel(top, text=r["name"], font=(FONT,14,"bold"),
                         text_color=TEXT).pack(side="left")
            tag_col = ACCENT2 if r["kind"] == "extractive" else ACCENT3
            ctk.CTkLabel(top, text=f"  {r['kind']}  ", font=(FONT,10),
                         text_color=tag_col, fg_color=SUR2,
                         corner_radius=6).pack(side="left", padx=8)
            if is_best:
                ctk.CTkLabel(top, text="  TỐT NHẤT  ", font=(FONT,10,"bold"),
                             text_color=BG, fg_color=ACCENT,
                             corner_radius=6).pack(side="left")

            if r["error"]:
                ctk.CTkLabel(card, text=f"Lỗi: {r['error']}", font=(FONT,12),
                             text_color=DANGER, anchor="w", justify="left",
                             wraplength=820).pack(anchor="w", padx=14, pady=(0,10))
                continue

            chips = ctk.CTkFrame(card, fg_color="transparent")
            chips.pack(fill="x", padx=12, pady=(0,4))
            for txt in [f"Nén {r['compress']}%", f"{r['n_sent']} câu",
                        f"{r['seconds']}s", f"Phủ KW {int(r['coverage'])}%"]:
                ctk.CTkLabel(chips, text=f"  {txt}  ", font=(MONO,11),
                             text_color=MUTED, fg_color=SUR2,
                             corner_radius=6).pack(side="left", padx=4, pady=2)

            body_txt = r["summary"].strip() or "(không có kết quả)"
            ctk.CTkLabel(card, text=body_txt, font=(FONT,12), text_color=MUTED,
                         anchor="w", justify="left",
                         wraplength=820).pack(anchor="w", padx=14, pady=(2,10))


    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: SCAN
    # ══════════════════════════════════════════════════════════════════════════
    def _build_scan_page(self, parent):
        parent.columnconfigure(0, weight=4, minsize=300)
        parent.columnconfigure(1, weight=6)
        parent.rowconfigure(0, weight=1)

        # ── Left config ──
        left = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=14,
                            border_width=1, border_color=BORDER)
        left.grid(row=0, column=0, sticky="nsew", padx=(12,6), pady=12)
        self._build_scan_config(left)

        # ── Right output ──
        right = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=14,
                             border_width=1, border_color=BORDER)
        right.grid(row=0, column=1, sticky="nsew", padx=(6,12), pady=12)
        self._build_scan_output(right)

    def _build_scan_config(self, parent):
        self.file_path    = tk.StringVar()
        self.lang_var     = tk.StringVar(value="en")
        self.num_sent     = tk.IntVar(value=3)
        self.input_mode   = tk.StringVar(value="file")   # "file" | "text"
        self.auto_card    = tk.BooleanVar(value=True)
        self.summary_mode = tk.StringVar(value="sent")   # "sent" | "pct"
        self.pct_val      = tk.DoubleVar(value=0.20)     # 10%–50%

        hdr = ctk.CTkFrame(parent, fg_color=SUR2, corner_radius=0, height=42)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="● CẤU HÌNH", font=(FONT,13,"bold"),
                     text_color=ACCENT).pack(side="left", padx=14)

        sc = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        sc.pack(fill="both", expand=True, padx=4, pady=4)

        def lbl(t): ctk.CTkLabel(sc, text=t, font=(FONT,12,"bold"),
                                  text_color=MUTED).pack(anchor="w", padx=12, pady=(12,4))

        # ── Input mode toggle ──
        lbl("NGUỒN ĐẦU VÀO")
        mode_frame = ctk.CTkFrame(sc, fg_color="transparent")
        mode_frame.pack(fill="x", padx=12, pady=(0,6))
        ctk.CTkSegmentedButton(
            mode_frame,
            values=["Chọn file", "Nhập văn bản"],
            variable=self.input_mode,
            font=(FONT,13),
            fg_color=SUR2, selected_color=ACCENT,
            selected_hover_color=ACCENT_H,
            unselected_color=SUR2, unselected_hover_color=BORDER,
            text_color=TEXT,
            command=self._on_input_mode_change
        ).pack(fill="x")

        # ── Container cố định giữ vị trí đúng trong layout ──
        self._input_container = ctk.CTkFrame(sc, fg_color="transparent")
        self._input_container.pack(fill="x", pady=(0,2))

        # ── File picker section (hiển thị mặc định) ──
        self._file_section = ctk.CTkFrame(self._input_container, fg_color="transparent")
        self._file_section.pack(fill="x")

        fr = ctk.CTkFrame(self._file_section, fg_color=SUR2, corner_radius=8,
                          border_width=1, border_color=BORDER)
        fr.pack(fill="x", padx=12, pady=(0,2))
        self.file_lbl = ctk.CTkLabel(fr, text="Chưa chọn file...",
                                     font=(FONT,13), text_color=MUTED,
                                     anchor="w", wraplength=150)
        self.file_lbl.pack(side="left", padx=10, pady=10, fill="x", expand=True)
        ctk.CTkButton(fr, text="Chọn", width=60, height=32,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      font=(FONT,13,"bold"),
                      command=self._pick_file).pack(side="right", padx=6, pady=6)

        self.file_info_lbl = ctk.CTkLabel(
            self._file_section, text="", font=(FONT,11),
            text_color=MUTED, anchor="w")
        self.file_info_lbl.pack(anchor="w", padx=14, pady=(0,2))

        # ── Direct text input section (ẩn mặc định) ──
        self._text_section = ctk.CTkFrame(self._input_container, fg_color="transparent")
        # Không pack — chỉ hiện khi chuyển sang text mode

        ctk.CTkLabel(self._text_section, text="Dán / nhập văn bản vào ô bên dưới:",
                     font=(FONT,12), text_color=MUTED
                     ).pack(anchor="w", padx=12, pady=(2,2))
        self.direct_text = ctk.CTkTextbox(
            self._text_section, height=140,
            fg_color=SUR2, text_color=TEXT,
            font=(FONT,13), border_color=BORDER,
            border_width=1, wrap="word")
        self.direct_text.pack(fill="x", padx=12, pady=(0,4))

        btn_row = ctk.CTkFrame(self._text_section, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0,2))
        ctk.CTkButton(btn_row, text="Xoá text", width=80, height=28,
                      fg_color=SUR2, hover_color=BORDER,
                      text_color=MUTED, font=(FONT,12),
                      command=lambda: self.direct_text.delete("1.0","end")
                      ).pack(side="right")

        # Language
        lbl("NGÔN NGỮ")
        lf = ctk.CTkFrame(sc, fg_color="transparent")
        lf.pack(fill="x", padx=12)
        for t, v in [("Tiếng Việt","vi"), ("English","en")]:
            ctk.CTkRadioButton(lf, text=t, variable=self.lang_var, value=v,
                               font=(FONT,13), text_color=TEXT,
                               fg_color=ACCENT, border_color=BORDER
                               ).pack(side="left", padx=(0,20))

        # OCR engine (vi -> EasyOCR đọc đúng dấu; PaddleOCR rụng dấu tiếng Việt)
        lbl("ENGINE OCR")
        self.ocr_engine_var = tk.StringVar(value="Tự động")
        ctk.CTkOptionMenu(
            sc, variable=self.ocr_engine_var,
            values=["Tự động", "PaddleOCR", "EasyOCR", "Tesseract"],
            fg_color=SUR2, button_color=ACCENT, button_hover_color=ACCENT_H,
            font=(FONT,13), text_color=TEXT, dropdown_fg_color=SUR2,
            dropdown_text_color=TEXT, width=180
            ).pack(anchor="w", padx=12, pady=(0,2))

        # Summary mode toggle
        lbl("CHẾ ĐỘ TÓM TẮT")
        mode_row = ctk.CTkFrame(sc, fg_color="transparent")
        mode_row.pack(fill="x", padx=12, pady=(0,4))
        for t, v in [("Số câu","sent"), ("Phần trăm (%)","pct")]:
            ctk.CTkRadioButton(mode_row, text=t, variable=self.summary_mode, value=v,
                               font=(FONT,13), text_color=TEXT,
                               fg_color=ACCENT, border_color=BORDER,
                               command=self._on_summary_mode_change
                               ).pack(side="left", padx=(0,20))

        # Container for the two slider variants
        self._summary_ctrl_frame = ctk.CTkFrame(sc, fg_color="transparent")
        self._summary_ctrl_frame.pack(fill="x", padx=12)

        # Sentence count slider
        self._sent_ctrl = ctk.CTkFrame(self._summary_ctrl_frame, fg_color="transparent")
        self._sent_ctrl.pack(fill="x")
        self.sent_lbl = ctk.CTkLabel(self._sent_ctrl, text="3",
                                     font=(FONT,17,"bold"),
                                     text_color=ACCENT, width=32)
        self.sent_lbl.pack(side="right")
        ctk.CTkSlider(self._sent_ctrl, from_=1, to=10, number_of_steps=9,
                      variable=self.num_sent, fg_color=BORDER,
                      progress_color=ACCENT, button_color=ACCENT,
                      button_hover_color=ACCENT_H,
                      command=lambda v: self.sent_lbl.configure(text=str(int(v)))
                      ).pack(side="left", fill="x", expand=True, padx=(0,8))

        # Percentage slider (hidden by default)
        self._pct_ctrl = ctk.CTkFrame(self._summary_ctrl_frame, fg_color="transparent")
        self.pct_lbl = ctk.CTkLabel(self._pct_ctrl, text="20%",
                                    font=(FONT,17,"bold"),
                                    text_color=ACCENT, width=42)
        self.pct_lbl.pack(side="right")
        ctk.CTkSlider(self._pct_ctrl, from_=0.10, to=0.50, number_of_steps=8,
                      variable=self.pct_val, fg_color=BORDER,
                      progress_color=ACCENT, button_color=ACCENT,
                      button_hover_color=ACCENT_H,
                      command=lambda v: self.pct_lbl.configure(text=f"{int(round(v,1)*100)}%")
                      ).pack(side="left", fill="x", expand=True, padx=(0,8))

        # Auto flashcard
        lbl("TÙY CHỌN")
        ctk.CTkCheckBox(sc, text="Tự động tạo Flashcard sau khi scan",
                        variable=self.auto_card, font=(FONT,13),
                        text_color=TEXT, fg_color=ACCENT2, border_color=BORDER,
                        hover_color=ACCENT2, checkmark_color="black"
                        ).pack(anchor="w", padx=12, pady=2)

        # Run button
        self.run_btn = ctk.CTkButton(sc, text="Scan & Tóm tắt",
                                     height=48, fg_color=ACCENT,
                                     hover_color=ACCENT_H,
                                     font=(FONT,15,"bold"),
                                     corner_radius=10,
                                     command=self._run_scan)
        self.run_btn.pack(fill="x", padx=12, pady=14)

        self.status_lbl = ctk.CTkLabel(sc, text="", font=(FONT,12),
                                       text_color=MUTED)
        self.status_lbl.pack(pady=(0,6))

    def _build_scan_output(self, parent):
        hdr = ctk.CTkFrame(parent, fg_color=SUR2, corner_radius=0, height=38)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="● KẾT QUẢ", font=(FONT,13,"bold"),
                     text_color=ACCENT2).pack(side="left", padx=14)
        ctk.CTkButton(hdr, text="Lưu .txt", width=75, height=28,
                      fg_color=SUR2, hover_color=BORDER,
                      font=(FONT,12), text_color=MUTED,
                      command=self._save_result).pack(side="right", padx=6)
        ctk.CTkButton(hdr, text="Xoá", width=55, height=28,
                      fg_color=SUR2, hover_color=BORDER,
                      font=(FONT,12), text_color=MUTED,
                      command=self._clear_output).pack(side="right", padx=2)

        # Log
        self.log_box = ctk.CTkTextbox(parent, height=80, fg_color=SUR2,
                                      text_color=ACCENT2, font=(MONO,12),
                                      state="disabled", border_width=0)
        self.log_box.pack(fill="x", padx=10, pady=(8,0))

        # Output
        self.output = ctk.CTkTextbox(parent, fg_color=BG, text_color=TEXT,
                                     font=(FONT,14), wrap="word",
                                     state="disabled", border_width=0)
        self.output.pack(fill="both", expand=True, padx=10, pady=10)
        self.output.tag_config("h1",  foreground=ACCENT)
        self.output.tag_config("h2",  foreground=ACCENT2)
        self.output.tag_config("h3",  foreground=ACCENT3)
        self.output.tag_config("dot", foreground=ACCENT)
        self.output.tag_config("dim", foreground=MUTED)
        self.output.tag_config("sep", foreground=BORDER)

        self.scan_results = {}
        self._write_output([("dim", "\n  Chọn file và nhấn  "),
                            ("h1",  "Scan & Tóm tắt"),
                            ("dim", "  để bắt đầu\n")])

    # ── Scan actions ──────────────────────────────────────────────────────────
    def _on_input_mode_change(self, value):
        # Cả hai section đều là con của _input_container → pack/forget an toàn
        if value == "Chọn file":
            self.input_mode.set("file")
            self._text_section.pack_forget()
            self._file_section.pack(fill="x")
        else:
            self.input_mode.set("text")
            self._file_section.pack_forget()
            self._text_section.pack(fill="x")
            self.after(50, self.direct_text.focus_set)

    def _on_summary_mode_change(self):
        if self.summary_mode.get() == "sent":
            self._pct_ctrl.pack_forget()
            self._sent_ctrl.pack(fill="x")
        else:
            self._sent_ctrl.pack_forget()
            self._pct_ctrl.pack(fill="x")

    def _pick_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("Tất cả", "*.pdf *.png *.jpg *.jpeg *.bmp *.tiff *.docx *.xlsx *.pptx *.txt"),
                       ("PDF","*.pdf"),("Ảnh","*.png *.jpg *.jpeg"),
                       ("Word","*.docx"),("Excel","*.xlsx"),("PPT","*.pptx"),
                       ("Text","*.txt")])
        if path:
            self.file_path.set(path)
            self.file_lbl.configure(text=os.path.basename(path), text_color=TEXT)
            try:
                size = os.path.getsize(path)
                size_str = f"{size/1024:.1f} KB" if size < 1024*1024 else f"{size/1024/1024:.1f} MB"
                ext = os.path.splitext(path)[1].upper().lstrip(".")
                self.file_info_lbl.configure(
                    text=f"{ext}  ·  {size_str}", text_color=ACCENT2)
            except Exception:
                self.file_info_lbl.configure(text="")

    def _run_scan(self):
        if self.input_mode.get() == "file":
            path = self.file_path.get()
            if not path or not os.path.exists(path):
                messagebox.showerror("Lỗi", "Vui lòng chọn file hợp lệ!")
                return
        else:
            direct = self.direct_text.get("1.0", "end").strip()
            if not direct:
                messagebox.showerror("Lỗi", "Vui lòng nhập văn bản vào ô đầu vào!")
                return
        self.run_btn.configure(state="disabled", text="Đang xử lý…")
        self._clear_output()
        self.scan_results = {}
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        mode = self.input_mode.get()
        path = self.file_path.get()
        try:
            if mode == "file":
                _eng_map = {"Tự động": "auto", "PaddleOCR": "paddle",
                            "EasyOCR": "easyocr", "Tesseract": "tesseract"}
                engine = _eng_map.get(self.ocr_engine_var.get(), "auto")
                self._log("▶ " + os.path.basename(path))
                self._log(f"[*] Khởi tạo OCR (engine: {self.ocr_engine_var.get()})...")
                from Paddle_ocr_scanner import quick_scan

                self._log("[*] Đang scan file...")
                text = quick_scan(path, lang=self.lang_var.get(), engine=engine)
                if not text.strip():
                    self._log("[!] Không tìm thấy nội dung", "err"); return

                self._log(f"[✓] Scan xong: {len(text)} ký tự")

                import pathlib
                ftype = pathlib.Path(path).suffix.lower().lstrip(".")
                file_name = os.path.basename(path)
                lang = self.lang_var.get()
            else:
                # Chế độ nhập văn bản trực tiếp — bỏ qua OCR
                text = self.direct_text.get("1.0", "end").strip()
                self._log("▶ Văn bản nhập trực tiếp")
                self._log(f"[✓] Đã nhận: {len(text)} ký tự")
                ftype = "txt"
                file_name = f"text_{datetime.now().strftime('%H%M%S')}.txt"
                lang = self.lang_var.get()

            # Lưu scan vào DB
            scan_id = save_scan(file_name, text,
                                file_path=path if mode == "file" else "",
                                file_type=ftype, language=lang)

            from summarizer import (
                voting_summary, extract_keywords
            )
            if self.summary_mode.get() == "pct":
                import re as _re
                sents = _re.split(r'(?<=[.!?])\s+', text)
                n = max(1, int(len(sents) * self.pct_val.get()))
            else:
                n = self.num_sent.get()
            results = {"raw_text": text}

            if str(lang).startswith("vi"):
                self._log("[*] Tải mô hình từ khoá đa ngôn ngữ "
                          "(lần đầu có thể tải ~vài trăm MB, vui lòng đợi)...")
            else:
                self._log("[*] Trích xuất từ khoá (lần đầu cần tải mô hình)...")
            keywords = extract_keywords(text, top_n=15, lang=lang)
            results["keywords"] = "\n".join(f"• {k}" for k in keywords)
            save_keywords(scan_id, keywords)

            self._log("[*] Đang tóm tắt (voting)...")
            results["voting"] = voting_summary(text, n)

            # Lưu tóm tắt vào DB
            save_summaries_bulk(scan_id, results, n)

            # Tạo flashcard tự động
            card_count = 0
            if self.auto_card.get():
                self._log("[*] Tạo Flashcard tự động...")
                card_count = auto_generate_flashcards(scan_id, results, keywords)

            self._log(f"[✓] Hoàn thành! Đã tạo {card_count} flashcard", "ok")
            self.scan_results = results

            self.after(0, self._render_scan_results)
            self.after(0, self._refresh_stats)

        except Exception as e:
            self._log(f"[!] Lỗi: {e}", "err")
        finally:
            self.after(0, lambda: self.run_btn.configure(
                state="normal", text="Scan & Tóm tắt"))

    def _render_scan_results(self):
        self.output.configure(state="normal")
        self.output.delete("1.0","end")

        # ── Từ khoá ──
        kw = self.scan_results.get("keywords","")
        if kw:
            self.output.insert("end", "\n  TỪ KHOÁ\n", "h2")
            self.output.insert("end", f"{'─'*52}\n\n", "sep")
            for line in kw.split("\n"):
                if line.strip().startswith("•"):
                    self.output.insert("end", "  • ", "dot")
                    self.output.insert("end", line.lstrip("•").strip()+"\n")
            self.output.insert("end", "\n")

        # ── Kết quả tóm tắt tốt nhất ──
        voting = self.scan_results.get("voting","")
        if voting:
            self.output.insert("end", "  KẾT QUẢ TÓM TẮT\n", "h1")
            self.output.insert("end", f"{'─'*52}\n\n", "sep")
            for line in voting.split("\n"):
                if line.strip().startswith("•"):
                    self.output.insert("end", "  • ", "dot")
                    self.output.insert("end", line.lstrip("•").strip()+"\n")
                elif line.strip():
                    self.output.insert("end", "  "+line+"\n")
            self.output.insert("end", "\n")

        self.output.configure(state="disabled")

    def _log(self, msg, kind="run"):
        c = {"run":ACCENT,"ok":ACCENT2,"err":DANGER}.get(kind,TEXT)
        def _u():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg+"\n")
            self.log_box.configure(state="disabled")
            self.log_box.see("end")
            self.status_lbl.configure(text=msg, text_color=c)
        self.after(0, _u)

    def _write_output(self, parts):
        self.output.configure(state="normal")
        self.output.delete("1.0","end")
        for tag, text in parts:
            self.output.insert("end", text, tag)
        self.output.configure(state="disabled")

    def _clear_output(self):
        self.scan_results = {}
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0","end")
        self.log_box.configure(state="disabled")
        self._write_output([("dim","\n  Chọn file và nhấn  "),
                            ("h1","Scan & Tóm tắt"),
                            ("dim","  để bắt đầu\n")])

    def _save_result(self):
        if not self.scan_results:
            messagebox.showinfo("Thông báo","Chưa có kết quả!"); return
        default_name = ""
        if self.input_mode.get() == "file" and self.file_path.get():
            import os as _os
            default_name = _os.path.splitext(_os.path.basename(self.file_path.get()))[0]
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=default_name or "smartnote_export",
            filetypes=[("Text","*.txt")])
        if path:
            _export_txt(path, self.scan_results,
                        file_name=default_name or "Văn bản nhập trực tiếp")
            messagebox.showinfo("Đã lưu", path)


    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: HISTORY
    # ══════════════════════════════════════════════════════════════════════════
    def _build_history_page(self, parent):
        hdr = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=0, height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="Lịch sử Scan",
                     font=(FONT,13,"bold"), text_color=TEXT
                     ).pack(side="left", padx=16)
        ctk.CTkButton(hdr, text="Làm mới", width=90, height=30,
                      fg_color=SUR2, hover_color=BORDER, text_color=MUTED,
                      font=(FONT,12),
                      command=self._load_history).pack(side="right", padx=12)

        body = ctk.CTkFrame(parent, fg_color=BG)
        body.pack(fill="both", expand=True, padx=12, pady=8)
        body.columnconfigure(0, weight=3, minsize=280)
        body.columnconfigure(1, weight=7)
        body.rowconfigure(0, weight=1)

        # List
        lf = ctk.CTkFrame(body, fg_color=SURFACE, corner_radius=12,
                          border_width=1, border_color=BORDER)
        lf.grid(row=0,column=0,sticky="nsew",padx=(0,6))
        ctk.CTkLabel(lf, text="Danh sách file đã scan",
                     font=(FONT,13,"bold"), text_color=MUTED
                     ).pack(anchor="w", padx=12, pady=(10,4))

        self.hist_scroll = ctk.CTkScrollableFrame(lf, fg_color="transparent")
        self.hist_scroll.pack(fill="both", expand=True, padx=4)

        # Detail
        rf = ctk.CTkFrame(body, fg_color=SURFACE, corner_radius=12,
                          border_width=1, border_color=BORDER)
        rf.grid(row=0,column=1,sticky="nsew")

        rh = ctk.CTkFrame(rf, fg_color=SUR2, corner_radius=0, height=42)
        rh.pack(fill="x")
        rh.pack_propagate(False)
        ctk.CTkLabel(rh, text="Chi tiết", font=(FONT,13,"bold"),
                     text_color=MUTED).pack(side="left", padx=12)
        self.hist_del_btn = ctk.CTkButton(rh, text="Xoá", width=70,
                                          height=28, fg_color=SUR2,
                                          hover_color=DANGER,
                                          text_color=MUTED, font=(FONT,12),
                                          command=self._delete_history_item)
        self.hist_del_btn.pack(side="right", padx=8)
        ctk.CTkButton(rh, text="Xuất .txt", width=95, height=28,
                      fg_color=SUR2, hover_color=BORDER,
                      text_color=MUTED, font=(FONT,12),
                      command=self._export_history_item
                      ).pack(side="right", padx=2)

        self.hist_detail = ctk.CTkTextbox(rf, fg_color=BG, text_color=TEXT,
                                          font=(FONT,13), wrap="word",
                                          state="disabled", border_width=0)
        self.hist_detail.pack(fill="both", expand=True, padx=10, pady=10)

        self.selected_scan_id = None

    def _load_history(self):
        for w in self.hist_scroll.winfo_children():
            w.destroy()
        rows = get_all_scans()
        if not rows:
            ctk.CTkLabel(self.hist_scroll, text="Chưa có lịch sử",
                         text_color=MUTED, font=(FONT,13)
                         ).pack(pady=20)
            return
        for row in rows:
            ext = (row["file_type"] or "txt").upper()[:4]
            btn = ctk.CTkButton(
                self.hist_scroll,
                text=f"[{ext}]  {row['file_name'][:28]}\n"
                     f"        {row['scanned_at'][:16]}   {row['char_count']} ký tự",
                anchor="w", height=58,
                fg_color=SUR2, hover_color=BORDER,
                text_color=TEXT, font=(FONT,12),
                corner_radius=8,
                command=lambda rid=row["id"]: self._show_history_detail(rid)
            )
            btn.pack(fill="x", pady=2)

    def _show_history_detail(self, scan_id):
        self.selected_scan_id = scan_id
        scan = get_scan(scan_id)
        summaries = get_summaries(scan_id)
        keywords = get_keywords(scan_id)

        self.hist_detail.configure(state="normal")
        self.hist_detail.delete("1.0","end")
        self.hist_detail.insert("end",
            f"{scan['file_name']}\n"
            f"Loại: {scan['file_type']}  |  Ngôn ngữ: {scan['language']}\n"
            f"Scan lúc: {scan['scanned_at']}\n"
            f"Độ dài: {scan['char_count']} ký tự\n\n")

        if keywords:
            self.hist_detail.insert("end","Từ khoá:\n")
            self.hist_detail.insert("end", "  " + "  •  ".join(keywords[:8]) + "\n\n")

        for s in summaries:
            self.hist_detail.insert("end",
                f"{'─'*40}\n{s['algorithm'].upper()}\n{'─'*40}\n{s['content']}\n\n")

        self.hist_detail.configure(state="disabled")

    def _delete_history_item(self):
        if not self.selected_scan_id:
            messagebox.showinfo("Thông báo","Chọn 1 mục để xoá!"); return
        if messagebox.askyesno("Xác nhận","Xoá scan này và toàn bộ dữ liệu liên quan?"):
            delete_scan(self.selected_scan_id)
            self.selected_scan_id = None
            self._load_history()
            self.hist_detail.configure(state="normal")
            self.hist_detail.delete("1.0","end")
            self.hist_detail.configure(state="disabled")
            self._refresh_stats()

    def _export_history_item(self):
        if not self.selected_scan_id:
            messagebox.showinfo("Thông báo","Chọn 1 mục để xuất!"); return
        scan = get_scan(self.selected_scan_id)
        summaries = get_summaries(self.selected_scan_id)
        keywords = get_keywords(self.selected_scan_id)

        results = {"raw_text": scan.get("raw_text", "")}
        results["keywords"] = "\n".join(f"• {k}" for k in keywords) if keywords else ""
        for s in summaries:
            results[s["algorithm"]] = s["content"]

        import os as _os
        default_name = _os.path.splitext(scan["file_name"])[0]
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[("Text","*.txt")])
        if path:
            _export_txt(path, results, file_name=scan["file_name"],
                        scan_meta={"language": scan.get("language",""),
                                   "char_count": scan.get("char_count","")})
            messagebox.showinfo("Đã xuất", path)


    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: FLASHCARD MANAGER
    # ══════════════════════════════════════════════════════════════════════════
    def _build_flashcard_page(self, parent):
        hdr = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=0, height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="Quản lý Flashcard",
                     font=(FONT,13,"bold"), text_color=TEXT
                     ).pack(side="left", padx=16)
        ctk.CTkButton(hdr, text="+ Thêm thẻ", width=100, height=30,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      font=(FONT,12,"bold"),
                      command=self._add_card_dialog
                      ).pack(side="right", padx=12)

        body = ctk.CTkFrame(parent, fg_color=BG)
        body.pack(fill="both", expand=True, padx=12, pady=8)
        body.columnconfigure(0, weight=3, minsize=260)
        body.columnconfigure(1, weight=7)
        body.rowconfigure(0, weight=1)

        # Deck list
        df = ctk.CTkFrame(body, fg_color=SURFACE, corner_radius=12,
                          border_width=1, border_color=BORDER)
        df.grid(row=0,column=0,sticky="nsew",padx=(0,6))
        ctk.CTkLabel(df, text="Bộ thẻ (Deck)",
                     font=(FONT,13,"bold"), text_color=MUTED
                     ).pack(anchor="w", padx=12, pady=(10,4))
        self.deck_scroll = ctk.CTkScrollableFrame(df, fg_color="transparent")
        self.deck_scroll.pack(fill="both", expand=True, padx=4)

        # Card list
        cf = ctk.CTkFrame(body, fg_color=SURFACE, corner_radius=12,
                          border_width=1, border_color=BORDER)
        cf.grid(row=0,column=1,sticky="nsew")

        ch = ctk.CTkFrame(cf, fg_color=SUR2, corner_radius=0, height=42)
        ch.pack(fill="x")
        ch.pack_propagate(False)
        self.deck_lbl = ctk.CTkLabel(ch, text="Tất cả thẻ",
                                     font=(FONT,13,"bold"), text_color=MUTED)
        self.deck_lbl.pack(side="left", padx=12)
        ctk.CTkButton(ch, text="Đổi tên", width=78, height=28,
                      fg_color=SUR2, hover_color=BORDER,
                      text_color=ACCENT, font=(FONT,12),
                      command=self._rename_deck_dialog
                      ).pack(side="left", padx=2)
        # Nút thao tác thẻ — chỉ hiện khi đã chọn 1 thẻ (bo góc + viền)
        self.del_card_btn = ctk.CTkButton(
            ch, text="Xoá thẻ", width=90, height=30,
            fg_color=SUR2, hover_color=DANGER,
            text_color=MUTED, font=(FONT,12),
            corner_radius=15, border_width=1, border_color=BORDER,
            command=self._delete_selected_card)
        self.edit_card_btn = ctk.CTkButton(
            ch, text="Sửa", width=65, height=30,
            fg_color=SUR2, hover_color=BORDER,
            text_color=MUTED, font=(FONT,12),
            corner_radius=15, border_width=1, border_color=BORDER,
            command=self._edit_card_dialog)
        self._set_card_actions(False)   # ẩn cho tới khi chọn thẻ

        self.card_scroll = ctk.CTkScrollableFrame(cf, fg_color="transparent")
        self.card_scroll.pack(fill="both", expand=True, padx=6, pady=6)

        self.selected_deck = None
        self.selected_card_id = None
        self._card_frames = {}   # card_id → frame widget

    def _load_flashcard_page(self):
        for w in self.deck_scroll.winfo_children(): w.destroy()

        # All decks
        ctk.CTkButton(self.deck_scroll, text="Tất cả",
                      anchor="w", height=42, fg_color=SUR2,
                      hover_color=BORDER, text_color=TEXT, font=(FONT,13),
                      command=lambda: self._load_cards(None)
                      ).pack(fill="x", pady=2)

        decks = get_decks()
        for row in decks:
            # Mỗi bộ thẻ: nút chọn (trái) + nút ✕ xoá cả bộ (phải)
            row_fr = ctk.CTkFrame(self.deck_scroll, fg_color="transparent")
            row_fr.pack(fill="x", pady=2)
            ctk.CTkButton(row_fr,
                          text=f"{row['deck']}   ({row['count']})",
                          anchor="w", height=42, fg_color=SUR2,
                          hover_color=BORDER, text_color=TEXT,
                          font=(FONT,13), corner_radius=8,
                          command=lambda d=row["deck"]: self._load_cards(d)
                          ).pack(side="left", fill="x", expand=True)
            # Nút ✕ chỉ hiện khi con trỏ rê vào hàng (xem _bind_deck_hover)
            xbtn = ctk.CTkButton(row_fr, text="✕", width=34, height=42,
                                 fg_color=SUR2, hover_color=DANGER,
                                 text_color=MUTED, font=(FONT,14,"bold"),
                                 corner_radius=8,
                                 command=lambda d=row["deck"]: self._delete_deck(d))
            self._bind_deck_hover(row_fr, xbtn)

        self._load_cards(None)

    @staticmethod
    def _bind_tree(widget, seq, func):
        """Gắn event cho widget và mọi widget con (CTk bọc canvas/label bên trong)."""
        widget.bind(seq, func, add="+")
        for child in widget.winfo_children():
            SmartNoteApp._bind_tree(child, seq, func)

    def _bind_deck_hover(self, row_fr, xbtn):
        """Hiện nút ✕ khi con trỏ nằm trong hàng bộ thẻ, ẩn khi rời đi."""
        def show(_=None):
            if not xbtn.winfo_ismapped():
                xbtn.pack(side="left", padx=(4,0))
        def check_hide():
            try:
                if not row_fr.winfo_exists():
                    return
                x, y = row_fr.winfo_pointerxy()
                rx, ry = row_fr.winfo_rootx(), row_fr.winfo_rooty()
                inside = (rx <= x <= rx + row_fr.winfo_width()
                          and ry <= y <= ry + row_fr.winfo_height())
                if not inside:
                    xbtn.pack_forget()
            except Exception:
                pass
        def hide(_=None):
            row_fr.after(60, check_hide)   # chờ chút để bỏ qua va chạm giữa các widget con
        self._bind_tree(row_fr, "<Enter>", show)
        self._bind_tree(row_fr, "<Leave>", hide)

    def _delete_deck(self, deck):
        cards = get_flashcards(deck=deck)
        n = len(cards)
        if not messagebox.askyesno(
                "Xác nhận",
                f"Xoá bộ thẻ \"{deck}\" cùng {n} thẻ bên trong?"):
            return
        delete_deck(deck)
        if self.selected_deck == deck:
            self.selected_deck = None
        self._load_flashcard_page()
        self._refresh_stats()

    def _load_cards(self, deck):
        self.selected_deck = deck
        self.selected_card_id = None
        self._card_frames = {}
        self._set_card_actions(False)   # chưa chọn thẻ -> ẩn nút thao tác
        self.deck_lbl.configure(text=deck or "Tất cả thẻ")
        for w in self.card_scroll.winfo_children(): w.destroy()

        cards = get_flashcards(deck=deck)
        if not cards:
            ctk.CTkLabel(self.card_scroll, text="Chưa có thẻ nào",
                         text_color=MUTED, font=(FONT,13)
                         ).pack(pady=20)
            return

        diff_colors = {0:MUTED, 1:ACCENT2, 2:ACCENT3, 3:DANGER}
        diff_labels = {0:"Mới", 1:"Dễ", 2:"Trung bình", 3:"Khó"}

        def bind_click(widget, cid):
            widget.bind("<Button-1>", lambda _e, c=cid: self._select_card(c))

        for card in cards:
            cf = ctk.CTkFrame(self.card_scroll, fg_color=SUR2, corner_radius=10,
                              border_width=1, border_color=BORDER)
            cf.pack(fill="x", pady=3)
            self._card_frames[card["id"]] = cf
            bind_click(cf, card["id"])

            top = ctk.CTkFrame(cf, fg_color="transparent")
            top.pack(fill="x", padx=10, pady=(8,2))
            bind_click(top, card["id"])

            front_txt = card["front"][:60]+"..." if len(card["front"])>60 else card["front"]
            lbl_front = ctk.CTkLabel(top, text=front_txt,
                         font=(FONT,13,"bold"), text_color=TEXT,
                         anchor="w", wraplength=400)
            lbl_front.pack(side="left", fill="x", expand=True)
            bind_click(lbl_front, card["id"])

            dc = diff_colors.get(card["difficulty"], MUTED)
            lbl_diff = ctk.CTkLabel(top, text=diff_labels.get(card["difficulty"],""),
                         font=(FONT,11), text_color=dc,
                         fg_color=SUR2, corner_radius=4)
            lbl_diff.pack(side="right")
            bind_click(lbl_diff, card["id"])

            back_txt = card["back"][:80]+"..." if len(card["back"])>80 else card["back"]
            lbl_back = ctk.CTkLabel(cf, text=back_txt,
                         font=(FONT,12), text_color=MUTED,
                         anchor="w", wraplength=450)
            lbl_back.pack(anchor="w", padx=10, pady=(0,8))
            bind_click(lbl_back, card["id"])

    def _set_card_actions(self, visible):
        """Hiện/ẩn nút Sửa + Xoá thẻ (chỉ dùng khi đã chọn 1 thẻ)."""
        if visible:
            self.del_card_btn.pack(side="right", padx=6)
            self.edit_card_btn.pack(side="right", padx=2)
        else:
            self.del_card_btn.pack_forget()
            self.edit_card_btn.pack_forget()

    def _select_card(self, card_id):
        # Bỏ highlight card cũ
        if self.selected_card_id and self.selected_card_id in self._card_frames:
            old = self._card_frames[self.selected_card_id]
            old.configure(border_color=BORDER, border_width=1)
        # Highlight card mới
        self.selected_card_id = card_id
        if card_id in self._card_frames:
            self._card_frames[card_id].configure(
                border_color=SUCCESS, border_width=2)
        self._set_card_actions(True)   # hiện nút thao tác thẻ

    def _rename_deck_dialog(self):
        # Chỉ đổi tên khi đang chọn 1 bộ thẻ cụ thể (không phải "Tất cả thẻ")
        if not self.selected_deck:
            messagebox.showinfo(
                "Thông báo",
                "Hãy chọn một bộ thẻ cụ thể ở danh sách bên trái để đổi tên!")
            return

        dlg = ctk.CTkInputDialog(
            title="Đổi tên bộ thẻ",
            text=f"Nhập tên mới cho bộ thẻ:\n\"{self.selected_deck}\"",
            fg_color=SURFACE, button_fg_color=ACCENT,
            button_hover_color=ACCENT_H, entry_fg_color=SUR2,
            entry_border_color=BORDER, entry_text_color=TEXT)
        new_name = (dlg.get_input() or "").strip()
        if not new_name or new_name == self.selected_deck:
            return

        n = rename_deck(self.selected_deck, new_name)
        self.selected_deck = new_name
        self._load_flashcard_page()   # dựng lại danh sách deck
        self._load_cards(new_name)    # mở lại đúng bộ vừa đổi tên
        self._refresh_stats()
        messagebox.showinfo("Đã đổi tên",
                            f"Đã cập nhật {n} thẻ sang bộ \"{new_name}\".")

    def _add_card_dialog(self):
        self._card_dialog(None)

    def _edit_card_dialog(self):
        if not self.selected_card_id:
            messagebox.showinfo("Thông báo","Hãy chọn thẻ cần sửa trước!"); return
        self._card_dialog(self.selected_card_id)

    def _card_dialog(self, card_id):
        win = ctk.CTkToplevel(self)
        win.title("Thêm Flashcard" if not card_id else "Sửa Flashcard")
        win.geometry("500x420")
        win.configure(fg_color=BG)
        win.grab_set()

        front_var = tk.StringVar()
        back_var  = tk.StringVar()
        hint_var  = tk.StringVar()
        deck_var  = tk.StringVar(value="General")

        if card_id:
            from database import get_conn
            conn = get_conn()
            c = conn.execute("SELECT * FROM flashcards WHERE id=?", (card_id,)).fetchone()
            conn.close()
            if c:
                front_var.set(c["front"])
                back_var.set(c["back"])
                hint_var.set(c["hint"] or "")
                deck_var.set(c["deck"])

        for lbl_txt, var, h in [
            ("Mặt trước (câu hỏi)", front_var, 80),
            ("Mặt sau (đáp án)",    back_var,  80),
            ("Gợi ý (tuỳ chọn)",   hint_var,  40),
        ]:
            ctk.CTkLabel(win, text=lbl_txt, font=(FONT,11,"bold"),
                         text_color=MUTED).pack(anchor="w", padx=16, pady=(12,2))
            tb = ctk.CTkTextbox(win, height=h, fg_color=SUR2,
                                border_color=BORDER, text_color=TEXT,
                                font=(FONT,11))
            tb.pack(fill="x", padx=16)
            tb.insert("1.0", var.get())
            # Gắn textbox vào var
            var._tb = tb

        ctk.CTkLabel(win, text="Deck", font=(FONT,11,"bold"),
                     text_color=MUTED).pack(anchor="w", padx=16, pady=(10,2))
        ctk.CTkEntry(win, textvariable=deck_var, fg_color=SUR2,
                     border_color=BORDER, text_color=TEXT,
                     font=(FONT,11), height=34
                     ).pack(fill="x", padx=16)

        def _save():
            front = front_var._tb.get("1.0","end").strip()
            back  = back_var._tb.get("1.0","end").strip()
            hint  = hint_var._tb.get("1.0","end").strip()
            deck  = deck_var.get().strip() or "General"
            if not front or not back:
                messagebox.showerror("Lỗi","Cần điền mặt trước và mặt sau!",parent=win)
                return
            if card_id:
                update_flashcard(card_id, front, back, hint, deck)
            else:
                add_flashcard(front, back, hint, deck)
            win.destroy()
            self._load_flashcard_page()
            self._refresh_stats()

        ctk.CTkButton(win, text="Lưu", height=40, fg_color=ACCENT,
                      hover_color=ACCENT_H, font=(FONT,12,"bold"),
                      command=_save).pack(fill="x", padx=16, pady=14)

    def _delete_selected_card(self):
        if not self.selected_card_id:
            messagebox.showinfo("Thông báo","Hãy chọn thẻ cần xoá trước!"); return
        if messagebox.askyesno("Xác nhận","Xoá flashcard này?"):
            delete_flashcard(self.selected_card_id)
            self.selected_card_id = None
            self._load_flashcard_page()
            self._refresh_stats()


    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: ÔN TẬP
    # ══════════════════════════════════════════════════════════════════════════
    def _build_review_page(self, parent):
        hdr = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=0, height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="Ôn tập Flashcard",
                     font=(FONT,13,"bold"), text_color=TEXT
                     ).pack(side="left", padx=16)

        self.review_body = ctk.CTkFrame(parent, fg_color=BG)
        self.review_body.pack(fill="both", expand=True, padx=20, pady=12)

        # Deck selector
        sel_frame = ctk.CTkFrame(self.review_body, fg_color=SURFACE,
                                 corner_radius=12, border_width=1, border_color=BORDER)
        sel_frame.pack(fill="x", pady=(0,12))

        ctk.CTkLabel(sel_frame, text="Chọn bộ thẻ để ôn:",
                     font=(FONT,11), text_color=MUTED
                     ).pack(side="left", padx=12, pady=10)

        self.review_deck_var = tk.StringVar(value="")
        self.review_deck_menu = ctk.CTkOptionMenu(
            sel_frame, variable=self.review_deck_var,
            values=["(tất cả)"],
            fg_color=SUR2, button_color=ACCENT,
            font=(FONT,11), text_color=TEXT,
            width=180)
        self.review_deck_menu.pack(side="left", padx=8, pady=8)

        ctk.CTkButton(sel_frame, text="▶  Bắt đầu ôn", width=110, height=34,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      font=(FONT,11,"bold"),
                      command=self._start_review
                      ).pack(side="left", padx=8)

        self.review_stats_lbl = ctk.CTkLabel(sel_frame, text="",
                                             font=(FONT,10), text_color=MUTED)
        self.review_stats_lbl.pack(side="right", padx=12)

        # Card display
        self.card_frame = ctk.CTkFrame(self.review_body, fg_color=SURFACE,
                                       corner_radius=16, border_width=1,
                                       border_color=BORDER)
        self.card_frame.pack(fill="both", expand=True)

        self.card_front_lbl = ctk.CTkLabel(
            self.card_frame, text="",
            font=(FONT,18,"bold"), text_color=TEXT,
            wraplength=700, justify="center")
        self.card_front_lbl.pack(expand=True, pady=(40,10))

        self.card_hint_lbl = ctk.CTkLabel(
            self.card_frame, text="",
            font=(FONT,12), text_color=MUTED,
            wraplength=600, justify="center")
        self.card_hint_lbl.pack(pady=(0,10))

        self.flip_btn = ctk.CTkButton(
            self.card_frame, text="Xem đáp án",
            width=170, height=42,
            fg_color=SUR2, hover_color=BORDER,
            font=(FONT,13,"bold"), text_color=TEXT,
            corner_radius=10,
            command=self._flip_card)
        self.flip_btn.pack(pady=10)

        self.card_back_frame = ctk.CTkFrame(self.card_frame, fg_color=SUR2,
                                            corner_radius=12)

        self.card_back_lbl = ctk.CTkLabel(
            self.card_back_frame, text="",
            font=(FONT,14), text_color=ACCENT2,
            wraplength=650, justify="center")
        self.card_back_lbl.pack(padx=20, pady=20)

        # Answer buttons
        self.answer_frame = ctk.CTkFrame(self.card_frame, fg_color="transparent")

        # (label, result, bg, hover, text-color)
        for txt, result, color, hover, tcol in [
            ("Chưa nhớ", "wrong",   DANGER, "#cf564f", "white"),
            ("Bỏ qua",   "skip",    SUR2,   BORDER,    MUTED),
            ("Đã nhớ",   "correct", ACCENT, ACCENT_H,  "white"),
        ]:
            ctk.CTkButton(self.answer_frame, text=txt, width=132, height=42,
                          fg_color=color, hover_color=hover,
                          corner_radius=10,
                          font=(FONT,13,"bold"), text_color=tcol,
                          command=lambda r=result: self._answer(r)
                          ).pack(side="left", padx=8)

        self.progress_lbl = ctk.CTkLabel(
            self.card_frame, text="",
            font=(FONT,10), text_color=MUTED)
        self.progress_lbl.pack(side="bottom", pady=10)

        self.review_cards = []
        self.review_idx = 0
        self.review_score = {"correct":0,"wrong":0,"skip":0}

    def _load_review(self):
        decks = get_decks()
        vals = ["(tất cả)"] + [r["deck"] for r in decks]
        self.review_deck_menu.configure(values=vals)
        s = get_stats()
        self.review_stats_lbl.configure(
            text=f"⏰ {s['due_today']} card cần ôn hôm nay")

    def _start_review(self):
        deck = self.review_deck_var.get()
        if deck == "(tất cả)": deck = None
        self.review_cards = list(get_flashcards(deck=deck, due_only=False))
        if not self.review_cards:
            messagebox.showinfo("Thông báo","Không có flashcard nào!"); return
        self.review_idx = 0
        self.review_score = {"correct":0,"wrong":0,"skip":0}
        self._show_card()

    def _show_card(self):
        if self.review_idx >= len(self.review_cards):
            self._show_review_result(); return

        card = self.review_cards[self.review_idx]
        self.card_front_lbl.configure(text=card["front"])
        hint = card["hint"] or ""
        self.card_hint_lbl.configure(text=f"Gợi ý:  {hint}" if hint else "")
        self.card_back_lbl.configure(text=card["back"])
        self.card_back_frame.pack_forget()
        self.answer_frame.pack_forget()
        self.flip_btn.pack(pady=10)
        self.progress_lbl.configure(
            text=f"{self.review_idx+1} / {len(self.review_cards)}"
                 f"  ✓{self.review_score['correct']}  ✗{self.review_score['wrong']}")

    def _flip_card(self):
        self.flip_btn.pack_forget()
        self.card_back_frame.pack(fill="x", padx=40, pady=10)
        self.answer_frame.pack(pady=10)

    def _answer(self, result):
        card = self.review_cards[self.review_idx]
        record_review(card["id"], result)
        self.review_score[result] += 1
        self.review_idx += 1
        self._show_card()

    def _show_review_result(self):
        s = self.review_score
        total = sum(s.values())
        pct = int(s["correct"]/total*100) if total else 0
        self.card_front_lbl.configure(
            text=f"Hoàn thành\n\n"
                 f"Đã nhớ {s['correct']}    "
                 f"Chưa nhớ {s['wrong']}    "
                 f"Bỏ qua {s['skip']}\n\n"
                 f"Tỷ lệ đúng: {pct}%")
        self.card_hint_lbl.configure(text="")
        self.card_back_frame.pack_forget()
        self.answer_frame.pack_forget()
        self.flip_btn.pack_forget()
        self._refresh_stats()


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    init_db()
    app = SmartNoteApp()
    app.mainloop()
