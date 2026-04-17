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
    delete_flashcard, record_review, get_stats, delete_scan
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG      = "#0d0d14"
SURFACE = "#13131e"
SUR2    = "#1c1c2e"
BORDER  = "#2a2a40"
ACCENT  = "#7c6af7"
ACCENT2 = "#6af7c0"
ACCENT3 = "#f7c06a"
TEXT    = "#e8e8f0"
MUTED   = "#6b6b8a"
DANGER  = "#f76a6a"
SUCCESS = "#6af7c0"


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
        hdr = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(hdr, text="Smart", font=("Helvetica",20,"bold"),
                     text_color=TEXT).pack(side="left", padx=(20,0))
        ctk.CTkLabel(hdr, text="Note", font=("Helvetica",20,"bold"),
                     text_color=ACCENT).pack(side="left")
        ctk.CTkLabel(hdr, text="  OCR · Summary · Flashcard",
                     font=("Helvetica",11), text_color=MUTED).pack(side="left")

        # Stats badge
        self.stats_lbl = ctk.CTkLabel(hdr, text="",
                                      font=("Helvetica",10), text_color=MUTED)
        self.stats_lbl.pack(side="right", padx=20)
        self._refresh_stats()

    def _refresh_stats(self):
        s = get_stats()
        self.stats_lbl.configure(
            text=f"📄 {s['total_scans']} scans  "
                 f"📝 {s['total_cards']} cards  "
                 f"⏰ {s['due_today']} due today"
        )

    # ── Nav sidebar ───────────────────────────────────────────────────────────
    def _build_nav(self):
        self.nav = ctk.CTkFrame(self, fg_color=SURFACE, width=160, corner_radius=0)
        self.nav.pack(side="left", fill="y")
        self.nav.pack_propagate(False)

        self.nav_btns = {}
        pages = [
            ("🔍  Scan",      "scan"),
            ("📚  Lịch sử",   "history"),
            ("🃏  Flashcard", "flashcard"),
            ("📖  Ôn tập",    "review"),
        ]
        for label, key in pages:
            btn = ctk.CTkButton(
                self.nav, text=label, anchor="w",
                fg_color="transparent", hover_color=SUR2,
                text_color=MUTED, font=("Helvetica",12),
                height=44, corner_radius=0,
                command=lambda k=key: self._show_page(k)
            )
            btn.pack(fill="x", pady=1)
            self.nav_btns[key] = btn

    def _show_page(self, key):
        for k, btn in self.nav_btns.items():
            if k == key:
                btn.configure(fg_color=SUR2, text_color=TEXT)
            else:
                btn.configure(fg_color="transparent", text_color=MUTED)
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
        for key in ["scan","history","flashcard","review"]:
            frame = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
            self.pages[key] = frame

        self._build_scan_page(self.pages["scan"])
        self._build_history_page(self.pages["history"])
        self._build_flashcard_page(self.pages["flashcard"])
        self._build_review_page(self.pages["review"])


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
        self.file_path  = tk.StringVar()
        self.lang_var   = tk.StringVar(value="en")
        self.num_sent   = tk.IntVar(value=3)
        self.input_mode = tk.StringVar(value="file")   # "file" | "text"
        self.auto_card  = tk.BooleanVar(value=True)

        hdr = ctk.CTkFrame(parent, fg_color=SUR2, corner_radius=0, height=42)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="● CẤU HÌNH", font=("Helvetica",13,"bold"),
                     text_color=ACCENT).pack(side="left", padx=14)

        sc = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        sc.pack(fill="both", expand=True, padx=4, pady=4)

        def lbl(t): ctk.CTkLabel(sc, text=t, font=("Helvetica",12,"bold"),
                                  text_color=MUTED).pack(anchor="w", padx=12, pady=(12,4))

        # ── Input mode toggle ──
        lbl("NGUỒN ĐẦU VÀO")
        mode_frame = ctk.CTkFrame(sc, fg_color="transparent")
        mode_frame.pack(fill="x", padx=12, pady=(0,6))
        ctk.CTkSegmentedButton(
            mode_frame,
            values=["📁  File", "📝  Nhập văn bản"],
            variable=self.input_mode,
            font=("Helvetica",13),
            fg_color=SUR2, selected_color=ACCENT,
            selected_hover_color="#6055d4",
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
                                     font=("Helvetica",13), text_color=MUTED,
                                     anchor="w", wraplength=150)
        self.file_lbl.pack(side="left", padx=10, pady=10, fill="x", expand=True)
        ctk.CTkButton(fr, text="Chọn", width=60, height=32,
                      fg_color=ACCENT, hover_color="#6055d4",
                      font=("Helvetica",13,"bold"),
                      command=self._pick_file).pack(side="right", padx=6, pady=6)

        self.file_info_lbl = ctk.CTkLabel(
            self._file_section, text="", font=("Helvetica",11),
            text_color=MUTED, anchor="w")
        self.file_info_lbl.pack(anchor="w", padx=14, pady=(0,2))

        # ── Direct text input section (ẩn mặc định) ──
        self._text_section = ctk.CTkFrame(self._input_container, fg_color="transparent")
        # Không pack — chỉ hiện khi chuyển sang text mode

        ctk.CTkLabel(self._text_section, text="Dán / nhập văn bản vào ô bên dưới:",
                     font=("Helvetica",12), text_color=MUTED
                     ).pack(anchor="w", padx=12, pady=(2,2))
        self.direct_text = ctk.CTkTextbox(
            self._text_section, height=140,
            fg_color=SUR2, text_color=TEXT,
            font=("Helvetica",13), border_color=BORDER,
            border_width=1, wrap="word")
        self.direct_text.pack(fill="x", padx=12, pady=(0,4))

        btn_row = ctk.CTkFrame(self._text_section, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0,2))
        ctk.CTkButton(btn_row, text="Xoá text", width=80, height=28,
                      fg_color=SUR2, hover_color=BORDER,
                      text_color=MUTED, font=("Helvetica",12),
                      command=lambda: self.direct_text.delete("1.0","end")
                      ).pack(side="right")

        # Language
        lbl("NGÔN NGỮ")
        lf = ctk.CTkFrame(sc, fg_color="transparent")
        lf.pack(fill="x", padx=12)
        for t, v in [("Tiếng Việt","vi"), ("English","en")]:
            ctk.CTkRadioButton(lf, text=t, variable=self.lang_var, value=v,
                               font=("Helvetica",13), text_color=TEXT,
                               fg_color=ACCENT, border_color=BORDER
                               ).pack(side="left", padx=(0,20))

        # Num sentences
        lbl("SỐ CÂU TÓM TẮT")
        sf = ctk.CTkFrame(sc, fg_color="transparent")
        sf.pack(fill="x", padx=12)
        self.sent_lbl = ctk.CTkLabel(sf, text="3", font=("Helvetica",17,"bold"),
                                     text_color=ACCENT, width=32)
        self.sent_lbl.pack(side="right")
        ctk.CTkSlider(sf, from_=1, to=10, number_of_steps=9,
                      variable=self.num_sent, fg_color=BORDER,
                      progress_color=ACCENT, button_color=ACCENT,
                      button_hover_color="#6055d4",
                      command=lambda v: self.sent_lbl.configure(text=str(int(v)))
                      ).pack(side="left", fill="x", expand=True, padx=(0,8))

        # Auto flashcard
        lbl("TÙY CHỌN")
        ctk.CTkCheckBox(sc, text="Tự động tạo Flashcard sau khi scan",
                        variable=self.auto_card, font=("Helvetica",13),
                        text_color=TEXT, fg_color=ACCENT2, border_color=BORDER,
                        hover_color=ACCENT2, checkmark_color="black"
                        ).pack(anchor="w", padx=12, pady=2)

        # Run button
        self.run_btn = ctk.CTkButton(sc, text="▶  Scan & Tóm tắt",
                                     height=48, fg_color=ACCENT,
                                     hover_color="#6055d4",
                                     font=("Helvetica",16,"bold"),
                                     corner_radius=10,
                                     command=self._run_scan)
        self.run_btn.pack(fill="x", padx=12, pady=14)

        self.status_lbl = ctk.CTkLabel(sc, text="", font=("Helvetica",12),
                                       text_color=MUTED)
        self.status_lbl.pack(pady=(0,6))

    def _build_scan_output(self, parent):
        hdr = ctk.CTkFrame(parent, fg_color=SUR2, corner_radius=0, height=38)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="● KẾT QUẢ", font=("Helvetica",13,"bold"),
                     text_color=ACCENT2).pack(side="left", padx=14)
        ctk.CTkButton(hdr, text="Lưu .txt", width=75, height=28,
                      fg_color=SUR2, hover_color=BORDER,
                      font=("Helvetica",12), text_color=MUTED,
                      command=self._save_result).pack(side="right", padx=6)
        ctk.CTkButton(hdr, text="Xoá", width=55, height=28,
                      fg_color=SUR2, hover_color=BORDER,
                      font=("Helvetica",12), text_color=MUTED,
                      command=self._clear_output).pack(side="right", padx=2)

        # Log
        self.log_box = ctk.CTkTextbox(parent, height=80, fg_color=SUR2,
                                      text_color=ACCENT2, font=("Courier",12),
                                      state="disabled", border_width=0)
        self.log_box.pack(fill="x", padx=10, pady=(8,0))

        # Output
        self.output = ctk.CTkTextbox(parent, fg_color=BG, text_color=TEXT,
                                     font=("Helvetica",14), wrap="word",
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
                            ("h1",  "Scan & Summarize"),
                            ("dim", "  để bắt đầu\n")])

    # ── Scan actions ──────────────────────────────────────────────────────────
    def _on_input_mode_change(self, value):
        # Cả hai section đều là con của _input_container → pack/forget an toàn
        if value == "📁  File":
            self.input_mode.set("file")
            self._text_section.pack_forget()
            self._file_section.pack(fill="x")
        else:
            self.input_mode.set("text")
            self._file_section.pack_forget()
            self._text_section.pack(fill="x")
            self.after(50, self.direct_text.focus_set)

    def _pick_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("Tất cả", "*.pdf *.png *.jpg *.jpeg *.bmp *.tiff *.docx *.xlsx *.pptx"),
                       ("PDF","*.pdf"),("Ảnh","*.png *.jpg *.jpeg"),
                       ("Word","*.docx"),("Excel","*.xlsx"),("PPT","*.pptx")])
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
        self.run_btn.configure(state="disabled", text="⏳ Đang xử lý...")
        self._clear_output()
        self.scan_results = {}
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        mode = self.input_mode.get()
        path = self.file_path.get()
        try:
            if mode == "file":
                self._log("▶ " + os.path.basename(path))
                self._log("[*] Khởi tạo PaddleOCR...")
                from Paddle_ocr_scanner import quick_scan

                self._log("[*] Đang scan file...")
                text = quick_scan(path, lang=self.lang_var.get())
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
            n = self.num_sent.get()
            results = {"raw_text": text}

            self._log("[*] Trích xuất từ khoá...")
            keywords = extract_keywords(text, top_n=15)
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
                state="normal", text="▶  Scan & Summarize"))

    def _render_scan_results(self):
        self.output.configure(state="normal")
        self.output.delete("1.0","end")

        # ── Từ khoá ──
        kw = self.scan_results.get("keywords","")
        if kw:
            self.output.insert("end", "\n  🔑  TỪ KHOÁ\n", "h2")
            self.output.insert("end", f"{'─'*52}\n\n", "sep")
            for line in kw.split("\n"):
                if line.strip().startswith("•"):
                    self.output.insert("end", "  • ", "dot")
                    self.output.insert("end", line.lstrip("•").strip()+"\n")
            self.output.insert("end", "\n")

        # ── Kết quả tóm tắt tốt nhất ──
        voting = self.scan_results.get("voting","")
        if voting:
            self.output.insert("end", "  ⭐  KẾT QUẢ TÓM TẮT\n", "h1")
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
                            ("h1","Scan & Summarize"),
                            ("dim","  để bắt đầu\n")])

    def _save_result(self):
        if not self.scan_results:
            messagebox.showinfo("Thông báo","Chưa có kết quả!"); return
        path = filedialog.asksaveasfilename(defaultextension=".txt",
                                            filetypes=[("Text","*.txt")])
        if path:
            with open(path,"w",encoding="utf-8") as f:
                for k,v in self.scan_results.items():
                    if k=="raw_text": continue
                    f.write(f"{'='*50}\n{k.upper()}\n{'='*50}\n{v}\n\n")
            messagebox.showinfo("Đã lưu", path)


    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: HISTORY
    # ══════════════════════════════════════════════════════════════════════════
    def _build_history_page(self, parent):
        hdr = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=0, height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="📚  Lịch sử Scan",
                     font=("Helvetica",13,"bold"), text_color=TEXT
                     ).pack(side="left", padx=16)
        ctk.CTkButton(hdr, text="🔄 Làm mới", width=90, height=30,
                      fg_color=SUR2, hover_color=BORDER, text_color=MUTED,
                      font=("Helvetica",12),
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
                     font=("Helvetica",13,"bold"), text_color=MUTED
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
        ctk.CTkLabel(rh, text="Chi tiết", font=("Helvetica",13,"bold"),
                     text_color=MUTED).pack(side="left", padx=12)
        self.hist_del_btn = ctk.CTkButton(rh, text="🗑 Xoá", width=70,
                                          height=28, fg_color=SUR2,
                                          hover_color=DANGER,
                                          text_color=MUTED, font=("Helvetica",12),
                                          command=self._delete_history_item)
        self.hist_del_btn.pack(side="right", padx=8)

        self.hist_detail = ctk.CTkTextbox(rf, fg_color=BG, text_color=TEXT,
                                          font=("Helvetica",13), wrap="word",
                                          state="disabled", border_width=0)
        self.hist_detail.pack(fill="both", expand=True, padx=10, pady=10)

        self.selected_scan_id = None

    def _load_history(self):
        for w in self.hist_scroll.winfo_children():
            w.destroy()
        rows = get_all_scans()
        if not rows:
            ctk.CTkLabel(self.hist_scroll, text="Chưa có lịch sử",
                         text_color=MUTED, font=("Helvetica",13)
                         ).pack(pady=20)
            return
        icons = {"pdf":"📕","png":"🖼","jpg":"🖼","jpeg":"🖼","docx":"📝",
                 "xlsx":"📊","pptx":"📊"}
        for row in rows:
            ico = icons.get(row["file_type"],"📄")
            btn = ctk.CTkButton(
                self.hist_scroll,
                text=f"{ico}  {row['file_name'][:28]}\n"
                     f"     {row['scanned_at'][:16]}  {row['char_count']} chars",
                anchor="w", height=58,
                fg_color=SUR2, hover_color=BORDER,
                text_color=TEXT, font=("Helvetica",12),
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
            f"📄 {scan['file_name']}\n"
            f"Loại: {scan['file_type']}  |  Ngôn ngữ: {scan['language']}\n"
            f"Scan lúc: {scan['scanned_at']}\n"
            f"Độ dài: {scan['char_count']} ký tự\n\n")

        if keywords:
            self.hist_detail.insert("end","🔑 Từ khoá:\n")
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


    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: FLASHCARD MANAGER
    # ══════════════════════════════════════════════════════════════════════════
    def _build_flashcard_page(self, parent):
        hdr = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=0, height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="🃏  Quản lý Flashcard",
                     font=("Helvetica",13,"bold"), text_color=TEXT
                     ).pack(side="left", padx=16)
        ctk.CTkButton(hdr, text="+ Thêm card", width=100, height=30,
                      fg_color=ACCENT, hover_color="#6055d4",
                      font=("Helvetica",12,"bold"),
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
                     font=("Helvetica",13,"bold"), text_color=MUTED
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
        self.deck_lbl = ctk.CTkLabel(ch, text="Tất cả card",
                                     font=("Helvetica",13,"bold"), text_color=MUTED)
        self.deck_lbl.pack(side="left", padx=12)
        ctk.CTkButton(ch, text="🗑 Xoá card", width=90, height=28,
                      fg_color=SUR2, hover_color=DANGER,
                      text_color=MUTED, font=("Helvetica",12),
                      command=self._delete_selected_card
                      ).pack(side="right", padx=6)
        ctk.CTkButton(ch, text="✏ Sửa", width=65, height=28,
                      fg_color=SUR2, hover_color=BORDER,
                      text_color=MUTED, font=("Helvetica",12),
                      command=self._edit_card_dialog
                      ).pack(side="right", padx=2)

        self.card_scroll = ctk.CTkScrollableFrame(cf, fg_color="transparent")
        self.card_scroll.pack(fill="both", expand=True, padx=6, pady=6)

        self.selected_deck = None
        self.selected_card_id = None
        self._card_frames = {}   # card_id → frame widget

    def _load_flashcard_page(self):
        for w in self.deck_scroll.winfo_children(): w.destroy()

        # All decks
        ctk.CTkButton(self.deck_scroll, text="📦  Tất cả",
                      anchor="w", height=42, fg_color=SUR2,
                      hover_color=BORDER, text_color=TEXT, font=("Helvetica",13),
                      command=lambda: self._load_cards(None)
                      ).pack(fill="x", pady=2)

        decks = get_decks()
        for row in decks:
            ctk.CTkButton(self.deck_scroll,
                          text=f"🗂  {row['deck']}  ({row['count']})",
                          anchor="w", height=42, fg_color=SUR2,
                          hover_color=BORDER, text_color=TEXT,
                          font=("Helvetica",13),
                          command=lambda d=row["deck"]: self._load_cards(d)
                          ).pack(fill="x", pady=2)

        self._load_cards(None)

    def _load_cards(self, deck):
        self.selected_deck = deck
        self.selected_card_id = None
        self._card_frames = {}
        self.deck_lbl.configure(text=deck or "Tất cả card")
        for w in self.card_scroll.winfo_children(): w.destroy()

        cards = get_flashcards(deck=deck)
        if not cards:
            ctk.CTkLabel(self.card_scroll, text="Chưa có flashcard",
                         text_color=MUTED, font=("Helvetica",13)
                         ).pack(pady=20)
            return

        diff_colors = {0:MUTED, 1:ACCENT2, 2:ACCENT3, 3:DANGER}
        diff_labels = {0:"New", 1:"Easy", 2:"Medium", 3:"Hard"}

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
                         font=("Helvetica",13,"bold"), text_color=TEXT,
                         anchor="w", wraplength=400)
            lbl_front.pack(side="left", fill="x", expand=True)
            bind_click(lbl_front, card["id"])

            dc = diff_colors.get(card["difficulty"], MUTED)
            lbl_diff = ctk.CTkLabel(top, text=diff_labels.get(card["difficulty"],""),
                         font=("Helvetica",11), text_color=dc,
                         fg_color=SUR2, corner_radius=4)
            lbl_diff.pack(side="right")
            bind_click(lbl_diff, card["id"])

            back_txt = card["back"][:80]+"..." if len(card["back"])>80 else card["back"]
            lbl_back = ctk.CTkLabel(cf, text=back_txt,
                         font=("Helvetica",12), text_color=MUTED,
                         anchor="w", wraplength=450)
            lbl_back.pack(anchor="w", padx=10, pady=(0,8))
            bind_click(lbl_back, card["id"])

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

    def _add_card_dialog(self):
        self._card_dialog(None)

    def _edit_card_dialog(self):
        if not self.selected_card_id:
            messagebox.showinfo("Thông báo","Click vào card cần sửa trước!"); return
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
            ctk.CTkLabel(win, text=lbl_txt, font=("Helvetica",11,"bold"),
                         text_color=MUTED).pack(anchor="w", padx=16, pady=(12,2))
            tb = ctk.CTkTextbox(win, height=h, fg_color=SUR2,
                                border_color=BORDER, text_color=TEXT,
                                font=("Helvetica",11))
            tb.pack(fill="x", padx=16)
            tb.insert("1.0", var.get())
            # Gắn textbox vào var
            var._tb = tb

        ctk.CTkLabel(win, text="Deck", font=("Helvetica",11,"bold"),
                     text_color=MUTED).pack(anchor="w", padx=16, pady=(10,2))
        ctk.CTkEntry(win, textvariable=deck_var, fg_color=SUR2,
                     border_color=BORDER, text_color=TEXT,
                     font=("Helvetica",11), height=34
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

        ctk.CTkButton(win, text="💾  Lưu", height=40, fg_color=ACCENT,
                      hover_color="#6055d4", font=("Helvetica",12,"bold"),
                      command=_save).pack(fill="x", padx=16, pady=14)

    def _delete_selected_card(self):
        if not self.selected_card_id:
            messagebox.showinfo("Thông báo","Click vào card cần xoá trước!"); return
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
        ctk.CTkLabel(hdr, text="📖  Ôn tập Flashcard",
                     font=("Helvetica",13,"bold"), text_color=TEXT
                     ).pack(side="left", padx=16)

        self.review_body = ctk.CTkFrame(parent, fg_color=BG)
        self.review_body.pack(fill="both", expand=True, padx=20, pady=12)

        # Deck selector
        sel_frame = ctk.CTkFrame(self.review_body, fg_color=SURFACE,
                                 corner_radius=12, border_width=1, border_color=BORDER)
        sel_frame.pack(fill="x", pady=(0,12))

        ctk.CTkLabel(sel_frame, text="Chọn bộ thẻ để ôn:",
                     font=("Helvetica",11), text_color=MUTED
                     ).pack(side="left", padx=12, pady=10)

        self.review_deck_var = tk.StringVar(value="")
        self.review_deck_menu = ctk.CTkOptionMenu(
            sel_frame, variable=self.review_deck_var,
            values=["(tất cả)"],
            fg_color=SUR2, button_color=ACCENT,
            font=("Helvetica",11), text_color=TEXT,
            width=180)
        self.review_deck_menu.pack(side="left", padx=8, pady=8)

        ctk.CTkButton(sel_frame, text="▶  Bắt đầu ôn", width=110, height=34,
                      fg_color=ACCENT, hover_color="#6055d4",
                      font=("Helvetica",11,"bold"),
                      command=self._start_review
                      ).pack(side="left", padx=8)

        self.review_stats_lbl = ctk.CTkLabel(sel_frame, text="",
                                             font=("Helvetica",10), text_color=MUTED)
        self.review_stats_lbl.pack(side="right", padx=12)

        # Card display
        self.card_frame = ctk.CTkFrame(self.review_body, fg_color=SURFACE,
                                       corner_radius=16, border_width=1,
                                       border_color=BORDER)
        self.card_frame.pack(fill="both", expand=True)

        self.card_front_lbl = ctk.CTkLabel(
            self.card_frame, text="",
            font=("Helvetica",18,"bold"), text_color=TEXT,
            wraplength=700, justify="center")
        self.card_front_lbl.pack(expand=True, pady=(40,10))

        self.card_hint_lbl = ctk.CTkLabel(
            self.card_frame, text="",
            font=("Helvetica",12), text_color=MUTED,
            wraplength=600, justify="center")
        self.card_hint_lbl.pack(pady=(0,10))

        self.flip_btn = ctk.CTkButton(
            self.card_frame, text="👁  Xem đáp án",
            width=160, height=40,
            fg_color=SUR2, hover_color=BORDER,
            font=("Helvetica",12,"bold"), text_color=TEXT,
            command=self._flip_card)
        self.flip_btn.pack(pady=10)

        self.card_back_frame = ctk.CTkFrame(self.card_frame, fg_color=SUR2,
                                            corner_radius=12)

        self.card_back_lbl = ctk.CTkLabel(
            self.card_back_frame, text="",
            font=("Helvetica",14), text_color=ACCENT2,
            wraplength=650, justify="center")
        self.card_back_lbl.pack(padx=20, pady=20)

        # Answer buttons
        self.answer_frame = ctk.CTkFrame(self.card_frame, fg_color="transparent")

        for txt, result, color in [
            ("✗  Chưa nhớ", "wrong",   DANGER),
            ("◎  Bỏ qua",   "skip",    MUTED),
            ("✓  Đã nhớ",   "correct", ACCENT2),
        ]:
            ctk.CTkButton(self.answer_frame, text=txt, width=130, height=40,
                          fg_color=color, hover_color=color,
                          font=("Helvetica",12,"bold"), text_color="black" if color==ACCENT2 else "white",
                          command=lambda r=result: self._answer(r)
                          ).pack(side="left", padx=8)

        self.progress_lbl = ctk.CTkLabel(
            self.card_frame, text="",
            font=("Helvetica",10), text_color=MUTED)
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
        self.card_hint_lbl.configure(text=f"💡 {hint}" if hint else "")
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
            text=f"🎉  Hoàn thành!\n\n"
                 f"✓ Đã nhớ: {s['correct']}   "
                 f"✗ Chưa nhớ: {s['wrong']}   "
                 f"◎ Bỏ qua: {s['skip']}\n\n"
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
