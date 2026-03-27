"""
Cần cài: pip install customtkinter
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

try:
    import customtkinter as ctk
except ImportError:
    print("[!] Cần cài customtkinter: pip install customtkinter")
    sys.exit(1)

# ── Theme ──────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG       = "#0d0d14"
SURFACE  = "#13131e"
SURFACE2 = "#1c1c2e"
BORDER   = "#2a2a40"
ACCENT   = "#7c6af7"
ACCENT2  = "#6af7c0"
ACCENT3  = "#f7c06a"
TEXT     = "#e8e8f0"
MUTED    = "#6b6b8a"
DANGER   = "#f76a6a"


# ── App ────────────────────────────────────────────────────────────────────────
class SmartNotes(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SmartNotes — OCR & Summarizer")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.configure(fg_color=BG)

        self.file_path = tk.StringVar(value="")
        self.lang_var  = tk.StringVar(value="en")
        self.num_sent  = tk.IntVar(value=3)
        self.api_key   = tk.StringVar(value="")
        self.use_lsa   = tk.BooleanVar(value=True)
        self.use_tr    = tk.BooleanVar(value=True)
        self.use_tt    = tk.BooleanVar(value=True)
        self.use_vote  = tk.BooleanVar(value=True)
        self.use_gem   = tk.BooleanVar(value=False)
        self.use_topic = tk.BooleanVar(value=True)

        self._build_ui()

    # ── UI ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ──
        hdr = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=56)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        ctk.CTkLabel(hdr, text="Scan", font=("Helvetica", 20, "bold"),
                     text_color=TEXT).pack(side="left", padx=(20,0), pady=12)
        ctk.CTkLabel(hdr, text="Sum", font=("Helvetica", 20, "bold"),
                     text_color=ACCENT).pack(side="left", pady=12)
        ctk.CTkLabel(hdr, text="  OCR + Summarizer",
                     font=("Helvetica", 12), text_color=MUTED).pack(side="left", pady=12)

        badge = ctk.CTkLabel(hdr, text=" v1.0 ", font=("Helvetica", 10),
                             text_color=ACCENT, fg_color=SURFACE2,
                             corner_radius=10)
        badge.pack(side="right", padx=20, pady=16)

        # ── Body ──
        body = ctk.CTkFrame(self, fg_color=BG)
        body.pack(fill="both", expand=True, padx=16, pady=12)
        body.columnconfigure(0, weight=4, minsize=320)
        body.columnconfigure(1, weight=6)
        body.rowconfigure(0, weight=1)

        # Left panel
        left = ctk.CTkFrame(body, fg_color=SURFACE, corner_radius=14,
                            border_width=1, border_color=BORDER)
        left.grid(row=0, column=0, sticky="nsew", padx=(0,8))
        self._build_left(left)

        # Right panel
        right = ctk.CTkFrame(body, fg_color=SURFACE, corner_radius=14,
                             border_width=1, border_color=BORDER)
        right.grid(row=0, column=1, sticky="nsew")
        self._build_right(right)

    def _section(self, parent, title):
        ctk.CTkLabel(parent, text=title, font=("Helvetica", 10, "bold"),
                     text_color=MUTED).pack(anchor="w", padx=16, pady=(12,4))

    def _build_left(self, parent):
        parent.columnconfigure(0, weight=1)

        # Title
        th = ctk.CTkFrame(parent, fg_color=SURFACE2, corner_radius=0, height=40)
        th.pack(fill="x")
        th.pack_propagate(False)
        ctk.CTkLabel(th, text="● CẤU HÌNH", font=("Helvetica", 11, "bold"),
                     text_color=ACCENT).pack(side="left", padx=16)

        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        # ── File chọn ──
        self._section(scroll, "FILE ĐẦU VÀO")
        file_row = ctk.CTkFrame(scroll, fg_color=SURFACE2, corner_radius=10,
                                border_width=1, border_color=BORDER)
        file_row.pack(fill="x", padx=12, pady=(0,4))

        self.file_lbl = ctk.CTkLabel(file_row, textvariable=self.file_path,
                                     font=("Helvetica", 11), text_color=MUTED,
                                     wraplength=180, anchor="w",
                                     text="Chưa chọn file...")
        self.file_lbl.pack(side="left", padx=12, pady=10, fill="x", expand=True)

        ctk.CTkButton(file_row, text="Chọn", width=60, height=30,
                      fg_color=ACCENT, hover_color="#6055d4",
                      font=("Helvetica", 11, "bold"),
                      command=self._pick_file).pack(side="right", padx=8, pady=8)

        # ── Ngôn ngữ ──
        self._section(scroll, "NGÔN NGỮ OCR")
        lang_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        lang_frame.pack(fill="x", padx=12)

        for txt, val in [("Tiếng Việt","vi"), ("English","en"), ("中文","ch")]:
            rb = ctk.CTkRadioButton(lang_frame, text=txt, variable=self.lang_var,
                                    value=val, font=("Helvetica", 12),
                                    text_color=TEXT, fg_color=ACCENT,
                                    border_color=BORDER)
            rb.pack(side="left", padx=(0,12), pady=4)

        # ── Thuật toán ──
        self._section(scroll, "THUẬT TOÁN TÓM TẮT")
        algo_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        algo_frame.pack(fill="x", padx=12)
        algo_frame.columnconfigure((0,1), weight=1)

        algos = [
            ("Topic Sentences", self.use_topic, ACCENT, 0, 0),
            ("LSA",             self.use_lsa,   ACCENT, 0, 1),
            ("TextRank",        self.use_tr,    ACCENT2,1, 0),
            ("TextTeaser",      self.use_tt,    ACCENT3,1, 1),
        ]
        for txt, var, color, row, col in algos:
            cb = ctk.CTkCheckBox(algo_frame, text=txt, variable=var,
                                 font=("Helvetica", 11), text_color=TEXT,
                                 fg_color=color, border_color=BORDER,
                                 hover_color=color, checkmark_color="white")
            cb.grid(row=row, column=col, sticky="w", pady=4, padx=4)

        vote_frame = ctk.CTkFrame(scroll, fg_color=SURFACE2, corner_radius=8,
                                  border_width=1, border_color=BORDER)
        vote_frame.pack(fill="x", padx=12, pady=(4,0))
        ctk.CTkCheckBox(vote_frame, text="⭐  Voting (Kết hợp tất cả - Best)",
                        variable=self.use_vote,
                        font=("Helvetica", 12, "bold"), text_color=ACCENT3,
                        fg_color=ACCENT, border_color=BORDER,
                        hover_color=ACCENT, checkmark_color="white"
                        ).pack(anchor="w", padx=12, pady=8)

        gem_frame = ctk.CTkFrame(scroll, fg_color=SURFACE2, corner_radius=8,
                                 border_width=1, border_color=BORDER)
        gem_frame.pack(fill="x", padx=12, pady=4)
        ctk.CTkCheckBox(gem_frame, text="✨  Gemini AI (cần API key)",
                        variable=self.use_gem,
                        font=("Helvetica", 12), text_color=ACCENT3,
                        fg_color=ACCENT3, border_color=BORDER,
                        hover_color=ACCENT3, checkmark_color="black"
                        ).pack(anchor="w", padx=12, pady=8)

        # ── Số câu ──
        self._section(scroll, "SỐ CÂU TRÍCH XUẤT")
        sl_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        sl_frame.pack(fill="x", padx=12)

        self.sent_lbl = ctk.CTkLabel(sl_frame, text="3",
                                     font=("Helvetica", 16, "bold"),
                                     text_color=ACCENT, width=30)
        self.sent_lbl.pack(side="right")

        sl = ctk.CTkSlider(sl_frame, from_=1, to=10, number_of_steps=9,
                           variable=self.num_sent,
                           fg_color=BORDER, progress_color=ACCENT,
                           button_color=ACCENT, button_hover_color="#6055d4",
                           command=lambda v: self.sent_lbl.configure(text=str(int(v))))
        sl.pack(side="left", fill="x", expand=True, padx=(0,8))

        # ── API Key ──
        self._section(scroll, "GEMINI API KEY (tuỳ chọn)")
        self.key_entry = ctk.CTkEntry(scroll, textvariable=self.api_key,
                                      placeholder_text="AIza...",
                                      show="●", height=36,
                                      fg_color=SURFACE2, border_color=BORDER,
                                      text_color=TEXT, font=("Courier", 12))
        self.key_entry.pack(fill="x", padx=12, pady=(0,8))

        # ── Run button ──
        self.run_btn = ctk.CTkButton(
            scroll,
            text="▶  Scan & Summarize",
            height=46,
            fg_color=ACCENT,
            hover_color="#6055d4",
            font=("Helvetica", 14, "bold"),
            corner_radius=10,
            command=self._run
        )
        self.run_btn.pack(fill="x", padx=12, pady=12)

        # Status
        self.status_lbl = ctk.CTkLabel(scroll, text="",
                                       font=("Helvetica", 11),
                                       text_color=MUTED)
        self.status_lbl.pack(pady=(0,8))

    def _build_right(self, parent):
        # Header
        th = ctk.CTkFrame(parent, fg_color=SURFACE2, corner_radius=0, height=40)
        th.pack(fill="x")
        th.pack_propagate(False)
        ctk.CTkLabel(th, text="● KẾT QUẢ", font=("Helvetica", 11, "bold"),
                     text_color=ACCENT2).pack(side="left", padx=16)
        ctk.CTkButton(th, text="Xoá", width=50, height=26,
                      fg_color=SURFACE, hover_color=BORDER,
                      font=("Helvetica", 10), text_color=MUTED,
                      command=self._clear).pack(side="right", padx=12)
        ctk.CTkButton(th, text="Lưu .txt", width=70, height=26,
                      fg_color=SURFACE, hover_color=BORDER,
                      font=("Helvetica", 10), text_color=MUTED,
                      command=self._save).pack(side="right", padx=4)

        # Tab bar
        tab_frame = ctk.CTkFrame(parent, fg_color=SURFACE2, corner_radius=0, height=36)
        tab_frame.pack(fill="x")
        tab_frame.pack_propagate(False)

        self.tab_var = tk.StringVar(value="all")
        tabs = [("Tất cả","all"),("Topic","topics"),("LSA","lsa"),
                ("TextRank","textrank"),("TextTeaser","textteaser"),
                ("⭐ Voting","voting"),("✨ Gemini","gemini"),("Raw OCR","raw")]
        self.tab_btns = {}
        for txt, val in tabs:
            btn = ctk.CTkButton(tab_frame, text=txt, width=70, height=28,
                                fg_color=ACCENT if val=="all" else "transparent",
                                hover_color=BORDER,
                                font=("Helvetica", 10),
                                text_color=TEXT if val=="all" else MUTED,
                                command=lambda v=val: self._switch_tab(v))
            btn.pack(side="left", padx=2, pady=4)
            self.tab_btns[val] = btn

        # Log area
        self.log_frame = ctk.CTkFrame(parent, fg_color=SURFACE2,
                                      corner_radius=0, height=0)
        self.log_frame.pack(fill="x")

        self.log_text = ctk.CTkTextbox(self.log_frame, height=0,
                                       fg_color=SURFACE2, text_color=ACCENT2,
                                       font=("Courier", 10), state="disabled",
                                       border_width=0)

        # Output textbox
        self.output = ctk.CTkTextbox(
            parent,
            fg_color=BG,
            text_color=TEXT,
            font=("Courier", 12),
            wrap="word",
            state="disabled",
            border_width=0,
            scrollbar_button_color=BORDER,
        )
        self.output.pack(fill="both", expand=True, padx=12, pady=12)

        # Tag config
        self.output.tag_config("header",  foreground=ACCENT)
        self.output.tag_config("header2", foreground=ACCENT2)
        self.output.tag_config("header3", foreground=ACCENT3)
        self.output.tag_config("bullet",  foreground=ACCENT)
        self.output.tag_config("muted",   foreground=MUTED)
        self.output.tag_config("sep",     foreground=BORDER)

        self._show_placeholder()

        self.results = {}

    # ── Actions ─────────────────────────────────────────────────────────────

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Chọn file để scan",
            filetypes=[
                ("Tất cả hỗ trợ", "*.pdf *.png *.jpg *.jpeg *.bmp *.tiff *.docx *.xlsx *.pptx"),
                ("PDF", "*.pdf"),
                ("Ảnh", "*.png *.jpg *.jpeg *.bmp *.tiff"),
                ("Word", "*.docx"),
                ("Excel", "*.xlsx"),
                ("PowerPoint", "*.pptx"),
            ]
        )
        if path:
            self.file_path.set(path)
            name = os.path.basename(path)
            self.file_lbl.configure(text=name, text_color=TEXT)

    def _run(self):
        path = self.file_path.get()
        if not path or not os.path.exists(path):
            messagebox.showerror("Lỗi", "Vui lòng chọn file hợp lệ!")
            return

        self.run_btn.configure(state="disabled", text="⏳ Đang xử lý...")
        self._clear()
        self._show_log(True)
        self._log("▶ Bắt đầu xử lý: " + os.path.basename(path))
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            self._log("[*] Khởi tạo PaddleOCR...")
            from Paddle_ocr_scanner import quick_scan

            self._log("[*] Đang scan file...")
            text = quick_scan(self.file_path.get(), lang=self.lang_var.get())

            if not text.strip():
                self._log("[!] Không tìm thấy nội dung trong file", "err")
                self.after(0, self._done)
                return

            self._log(f"[✓] Scan xong: {len(text)} ký tự")
            self.results = {"raw": text}

            from summarizer import (
                topic_sentence_summary, lsa_summary, textrank_summary,
                textteaser_summary, voting_summary, abstractive_summary,
                clean_ocr_text
            )

            n = self.num_sent.get()

            if self.use_topic.get():
                self._log("[*] Đang chạy Topic Sentences...")
                self.results["topics"] = topic_sentence_summary(text, n)

            if self.use_lsa.get():
                self._log("[*] Đang chạy LSA...")
                self.results["lsa"] = lsa_summary(text, n)

            if self.use_tr.get():
                self._log("[*] Đang chạy TextRank...")
                self.results["textrank"] = textrank_summary(text, n)

            if self.use_tt.get():
                self._log("[*] Đang chạy TextTeaser...")
                self.results["textteaser"] = textteaser_summary(text, num_sentences=n)

            if self.use_vote.get():
                self._log("[*] Đang voting LSA + TextRank + TextTeaser...")
                self.results["voting"] = voting_summary(text, n)

            if self.use_gem.get():
                key = self.api_key.get().strip()
                if key:
                    self._log("[*] Đang tóm tắt bằng Gemini AI...")
                    self.results["gemini"] = abstractive_summary(text, key)
                else:
                    self._log("[!] Bỏ qua Gemini (chưa có API key)", "warn")

            self._log("[✓] Hoàn thành!", "ok")
            self.after(0, lambda: self._render_results("all"))

        except Exception as e:
            self._log(f"[!] Lỗi: {e}", "err")
        finally:
            self.after(0, self._done)

    def _done(self):
        self.run_btn.configure(state="normal", text="▶  Scan & Summarize")

    def _log(self, msg, kind="run"):
        colors = {"run": ACCENT, "ok": ACCENT2, "err": DANGER, "warn": ACCENT3}
        color  = colors.get(kind, TEXT)

        def _update():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.configure(state="disabled")
            self.log_text.see("end")
            self.status_lbl.configure(text=msg, text_color=color)
        self.after(0, _update)

    def _show_log(self, show):
        if show:
            self.log_frame.configure(height=100)
            self.log_text.configure(height=100)
            self.log_text.pack(fill="x", padx=0, pady=0)
        else:
            self.log_frame.configure(height=0)
            self.log_text.pack_forget()

    def _render_results(self, tab):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")

        sections = []
        if tab in ("all", "topics") and "topics" in self.results:
            sections.append(("TOPIC SENTENCES", self.results["topics"], "header"))
        if tab in ("all", "lsa") and "lsa" in self.results:
            sections.append(("LSA", self.results["lsa"], "header"))
        if tab in ("all", "textrank") and "textrank" in self.results:
            sections.append(("TEXTRANK", self.results["textrank"], "header2"))
        if tab in ("all", "textteaser") and "textteaser" in self.results:
            sections.append(("TEXTTEASER", self.results["textteaser"], "header3"))
        if tab in ("all", "voting") and "voting" in self.results:
            sections.append(("⭐ VOTING (Best)", self.results["voting"], "header3"))
        if tab in ("all", "gemini") and "gemini" in self.results:
            sections.append(("✨ GEMINI AI", self.results["gemini"], "header3"))
        if tab == "raw" and "raw" in self.results:
            sections.append(("RAW OCR TEXT", self.results["raw"], "header"))

        if not sections:
            self.output.insert("end", "\n  Không có kết quả cho tab này", "muted")
        else:
            for title, content, tag in sections:
                self.output.insert("end", f"\n{'─'*50}\n", "sep")
                self.output.insert("end", f"  {title}\n", tag)
                self.output.insert("end", f"{'─'*50}\n\n", "sep")
                if content:
                    for line in content.split("\n"):
                        if line.startswith("•"):
                            self.output.insert("end", "  • ", "bullet")
                            self.output.insert("end", line[1:].strip() + "\n")
                        else:
                            self.output.insert("end", "  " + line + "\n")
                else:
                    self.output.insert("end", "  (trống)\n", "muted")
                self.output.insert("end", "\n")

        self.output.configure(state="disabled")

    def _switch_tab(self, val):
        self.tab_var.set(val)
        for k, btn in self.tab_btns.items():
            if k == val:
                btn.configure(fg_color=ACCENT, text_color=TEXT)
            else:
                btn.configure(fg_color="transparent", text_color=MUTED)
        if self.results:
            self._render_results(val)

    def _show_placeholder(self):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("end", "\n\n\n")
        self.output.insert("end", "         🔍  Chọn file và nhấn\n", "muted")
        self.output.insert("end", "         Scan & Summarize\n", "header")
        self.output.insert("end", "         để bắt đầu\n", "muted")
        self.output.configure(state="disabled")

    def _clear(self):
        self.results = {}
        self._show_placeholder()
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _save(self):
        if not self.results:
            messagebox.showinfo("Thông báo", "Chưa có kết quả để lưu!")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt")],
            title="Lưu kết quả"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                for key, content in self.results.items():
                    if key == "raw": continue
                    f.write(f"{'='*60}\n{key.upper()}\n{'='*60}\n{content}\n\n")
            messagebox.showinfo("Đã lưu", f"Kết quả đã được lưu vào:\n{path}")


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = SmartNotes()
    app.mainloop()