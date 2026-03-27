"""
Summarizer - Tóm tắt văn bản từ kết quả OCR
Kết hợp: LSA + TextRank (extractive) + Gemini API (abstractive)
"""

import os
import re
import time


# ─── TỰ ĐỘNG TẢI NLTK DATA ────────────────────────────────────────────────────

def _ensure_nltk():
    import nltk
    for pkg, path in [("punkt", "tokenizers/punkt"),
                      ("punkt_tab", "tokenizers/punkt_tab"),
                      ("stopwords", "corpora/stopwords")]:
        try:
            nltk.data.find(path)
        except LookupError:
            print(f"[*] Tải NLTK data: {pkg}...")
            nltk.download(pkg, quiet=True)


# ─── LÀM SẠCH TEXT OCR ────────────────────────────────────────────────────────

def clean_ocr_text(text: str) -> str:
    """
    Làm sạch text OCR, GIỮ NGUYÊN cấu trúc đoạn văn.
    """
    # Tách theo đoạn (2+ dòng trống)
    paragraphs = re.split(r'\n{2,}', text)
    cleaned_paragraphs = []

    for para in paragraphs:
        lines = para.splitlines()
        merged_lines = []
        buffer = ""

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Ghép dòng bị wrap (không kết thúc bằng dấu câu)
            if buffer:
                if re.search(r'[.!?]$', buffer):
                    merged_lines.append(buffer)
                    buffer = line
                else:
                    buffer += " " + line
            else:
                buffer = line

        if buffer:
            merged_lines.append(buffer)

        para_text = " ".join(merged_lines)
        # Bỏ ký tự nhiễu nhưng giữ dấu câu
        para_text = re.sub(r'[^\w\s.,!?;:\'\"-]', ' ', para_text)
        para_text = re.sub(r'\s+', ' ', para_text).strip()

        if para_text:
            if not para_text[-1] in '.!?':
                para_text += '.'
            cleaned_paragraphs.append(para_text)

    return "\n\n".join(cleaned_paragraphs)


# ─── TOPIC SENTENCES (câu chủ đề mỗi đoạn) ───────────────────────────────────

def topic_sentence_summary(text: str, max_sentences: int = 3) -> str:
    """
    Lấy câu đầu tiên của mỗi đoạn — phù hợp với bài luận có cấu trúc.
    """
    text = clean_ocr_text(text)
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    topic_sentences = []
    for para in paragraphs:
        sentences = re.split(r'(?<=[.!?])\s+', para)
        if sentences and sentences[0].strip():
            topic_sentences.append(sentences[0].strip())

    return "\n".join(f"• {s}" for s in topic_sentences[:max_sentences])


# ─── EXTRACTIVE: LSA ──────────────────────────────────────────────────────────

# ─── KEYBERT: Trích xuất từ khoá quan trọng ───────────────────────────────────

_keybert_model = None

def _get_keybert():
    """Lazy load KeyBERT (chỉ load 1 lần)."""
    global _keybert_model
    if _keybert_model is None:
        try:
            from keybert import KeyBERT
            print("[*] Đang load KeyBERT model...")
            _keybert_model = KeyBERT(model="all-MiniLM-L6-v2")
            print("[✓] KeyBERT sẵn sàng")
        except ImportError:
            print("[!] Cần cài: pip install keybert sentence-transformers")
    return _keybert_model


def extract_keywords(text: str, top_n: int = 10) -> list[str]:
    """
    Dùng KeyBERT trích xuất từ khoá quan trọng nhất.
    Trả về list các từ khoá theo thứ tự quan trọng giảm dần.
    """
    kb = _get_keybert()
    if not kb:
        return []
    try:
        cleaned = clean_ocr_text(text)
        # keyphrase_ngram_range=(1,2): lấy cả unigram và bigram
        # use_mmr=True: đảm bảo đa dạng từ khoá (không trùng lặp)
        keywords = kb.extract_keywords(
            cleaned,
            keyphrase_ngram_range=(1, 2),
            stop_words="english",
            use_mmr=True,
            diversity=0.5,
            top_n=top_n,
        )
        return [kw for kw, score in keywords]
    except Exception as e:
        print(f"[!] KeyBERT lỗi: {e}")
        return []


def _score_sentence_by_keywords(sentence: str, keywords: list[str]) -> float:
    """
    Tính điểm câu dựa trên mật độ từ khoá KeyBERT.
    Câu chứa nhiều từ khoá quan trọng → điểm cao hơn.
    """
    if not keywords:
        return 0.0
    s = sentence.lower()
    score = 0.0
    for i, kw in enumerate(keywords):
        # Từ khoá đứng đầu (quan trọng hơn) được trọng số cao hơn
        weight = 1.0 / (i + 1)
        if kw.lower() in s:
            score += weight
    return score


# ─── EXTRACTIVE: LSA + KeyBERT ────────────────────────────────────────────────

def lsa_summary(text: str, num_sentences: int = 3) -> str:
    """
    LSA cải tiến với KeyBERT:
    1. LSA chọn N*2 câu ứng viên
    2. KeyBERT trích xuất từ khoá quan trọng
    3. Rerank các câu ứng viên theo mật độ từ khoá
    4. Chọn top N câu sau rerank
    """
    _ensure_nltk()
    cleaned = clean_ocr_text(text)
    try:
        from sumy.parsers.plaintext import PlaintextParser
        from sumy.nlp.tokenizers import Tokenizer
        from sumy.summarizers.lsa import LsaSummarizer
        from sumy.nlp.stemmers import Stemmer
        from sumy.utils import get_stop_words

        parser = PlaintextParser.from_string(cleaned, Tokenizer("english"))
        stemmer = Stemmer("english")
        summarizer = LsaSummarizer(stemmer)
        summarizer.stop_words = get_stop_words("english")

        # Lấy nhiều hơn cần để rerank
        candidates = [str(s) for s in summarizer(parser.document, num_sentences * 2)]

        # KeyBERT rerank
        keywords = extract_keywords(cleaned, top_n=15)
        if keywords:
            scored = [(s, _score_sentence_by_keywords(s, keywords)) for s in candidates]
            scored.sort(key=lambda x: -x[1])
            # Giữ thứ tự xuất hiện trong văn bản gốc
            top_set = set(s for s, _ in scored[:num_sentences])
            all_sents = [str(s) for s in parser.document.sentences]
            ordered = [s for s in all_sents if s in top_set]
        else:
            # Fallback không có KeyBERT
            ordered = candidates[:num_sentences]

        return "\n".join(f"• {s}" for s in ordered)
    except Exception as e:
        print(f"[!] LSA lỗi: {e}")
        return ""


# ─── EXTRACTIVE: TEXTRANK + KeyBERT ──────────────────────────────────────────

def textrank_summary(text: str, num_sentences: int = 3) -> str:
    """
    TextRank cải tiến với KeyBERT:
    1. TextRank chọn N*2 câu ứng viên
    2. KeyBERT trích xuất từ khoá
    3. Rerank dựa trên điểm TextRank * điểm KeyBERT
    4. Chọn top N câu
    """
    _ensure_nltk()
    cleaned = clean_ocr_text(text)
    try:
        from sumy.parsers.plaintext import PlaintextParser
        from sumy.nlp.tokenizers import Tokenizer
        from sumy.summarizers.text_rank import TextRankSummarizer
        from sumy.nlp.stemmers import Stemmer
        from sumy.utils import get_stop_words

        parser = PlaintextParser.from_string(cleaned, Tokenizer("english"))
        stemmer = Stemmer("english")
        summarizer = TextRankSummarizer(stemmer)
        summarizer.stop_words = get_stop_words("english")

        candidates = [str(s) for s in summarizer(parser.document, num_sentences * 2)]

        # KeyBERT rerank
        keywords = extract_keywords(cleaned, top_n=15)
        if keywords:
            scored = [(s, _score_sentence_by_keywords(s, keywords)) for s in candidates]
            scored.sort(key=lambda x: -x[1])
            top_set = set(s for s, _ in scored[:num_sentences])
            all_sents = [str(s) for s in parser.document.sentences]
            ordered = [s for s in all_sents if s in top_set]
        else:
            ordered = candidates[:num_sentences]

        return "\n".join(f"• {s}" for s in ordered)
    except Exception as e:
        print(f"[!] TextRank lỗi: {e}")
        return ""


# ─── KEYBERT SUMMARY (độc lập) ────────────────────────────────────────────────

def keybert_summary(text: str, num_sentences: int = 3) -> str:
    """
    Tóm tắt thuần KeyBERT:
    Chấm điểm TẤT CẢ câu theo mật độ từ khoá, chọn top N.
    """
    _ensure_nltk()
    cleaned = clean_ocr_text(text)

    keywords = extract_keywords(cleaned, top_n=15)
    if not keywords:
        return ""

    # Tách câu
    sentences = re.split(r'(?<=[.!?])\s+', cleaned)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    if not sentences:
        return ""

    # Chấm điểm tất cả câu
    scored = [(s, _score_sentence_by_keywords(s, keywords)) for s in sentences]
    scored.sort(key=lambda x: -x[1])
    top_set = set(s for s, _ in scored[:num_sentences])

    # Giữ thứ tự xuất hiện
    ordered = [s for s in sentences if s in top_set]
    return "\n".join(f"• {s}" for s in ordered)


# ─── EXTRACTIVE: KẾT HỢP LSA + TEXTRANK (giữ lại cho voting) ─────────────────

def combined_extractive(text: str, num_sentences: int = 3) -> str:
    _ensure_nltk()
    cleaned = clean_ocr_text(text)
    try:
        from sumy.parsers.plaintext import PlaintextParser
        from sumy.nlp.tokenizers import Tokenizer
        from sumy.summarizers.lsa import LsaSummarizer
        from sumy.summarizers.text_rank import TextRankSummarizer
        from sumy.nlp.stemmers import Stemmer
        from sumy.utils import get_stop_words

        parser = PlaintextParser.from_string(cleaned, Tokenizer("english"))
        stemmer = Stemmer("english")
        stop_words = get_stop_words("english")

        lsa = LsaSummarizer(stemmer)
        lsa.stop_words = stop_words
        lsa_set = set(str(s) for s in lsa(parser.document, num_sentences))

        tr = TextRankSummarizer(stemmer)
        tr.stop_words = stop_words
        tr_set = set(str(s) for s in tr(parser.document, num_sentences))

        both = lsa_set & tr_set
        either = (lsa_set | tr_set) - both
        selected = both | set(list(either)[:max(0, num_sentences - len(both))])

        all_sentences = [str(s) for s in parser.document.sentences]
        ordered = [s for s in all_sentences if s in selected]
        return "\n".join(f"• {s}" for s in ordered)

    except Exception as e:
        print(f"[!] Combined lỗi: {e}")
        return lsa_summary(cleaned, num_sentences)


# ─── ABSTRACTIVE: GEMINI ──────────────────────────────────────────────────────

def _build_prompt(text: str, language: str) -> str:
    return f"""You are an expert at summarizing academic essays.
Summarize the following essay in {language} in 3-5 bullet points, focusing on:
- Main thesis/argument
- Key supporting points
- Conclusion

Be concise. Each bullet point = 1 key idea.

ESSAY:
{clean_ocr_text(text)[:4000]}

SUMMARY:"""


def abstractive_summary(text: str, api_key: str, language: str = "English") -> str:
    prompt = _build_prompt(text, language)

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model="gemini-2.0-flash", contents=prompt)
                return response.text
            except Exception as e:
                if "429" in str(e) and attempt < 2:
                    print(f"[!] Quota hết, chờ 20 giây... ({attempt+1}/3)")
                    time.sleep(20)
                else:
                    raise e
    except ImportError:
        pass

    try:
        import warnings
        warnings.filterwarnings("ignore")
        import google.generativeai as genai_old
        genai_old.configure(api_key=api_key)
        model = genai_old.GenerativeModel("gemini-2.0-flash")
        for attempt in range(3):
            try:
                response = model.generate_content(prompt)
                return response.text
            except Exception as e:
                if "429" in str(e) and attempt < 2:
                    print(f"[!] Quota hết, chờ 20 giây... ({attempt+1}/3)")
                    time.sleep(20)
                else:
                    return f"[!] Gemini lỗi: {e}"
    except Exception as e:
        return f"[!] Gemini lỗi: {e}"

    return "[!] Không thể kết nối Gemini"


# ─── HÀM CHÍNH ────────────────────────────────────────────────────────────────

# ─── TEXTTEASER ───────────────────────────────────────────────────────────────

def textteaser_summary(text: str, title: str = "", num_sentences: int = 3) -> str:
    """
    Dùng TextTeaser để tóm tắt.
    TextTeaser chấm điểm câu dựa trên:
    - Vị trí câu trong đoạn
    - Độ dài câu
    - Mức độ liên quan với tiêu đề
    - Keyword density

    Cài đặt trước:
        git clone https://github.com/IndigoResearch/textteaser.git
        Sau đó copy thư mục textteaser/textteaser/ vào cùng thư mục SourceCode/
    """
    try:
        from textteaser_lib import TextTeaser
    except ImportError:
        print("[!] TextTeaser chưa được cài. Xem hướng dẫn:")
        print("    git clone https://github.com/IndigoResearch/textteaser.git")
        print("    Copy thư mục textteaser/textteaser/ vào SourceCode/")
        return ""

    try:
        cleaned = clean_ocr_text(text)
        # TextTeaser cần title — dùng câu đầu tiên nếu không có
        if not title:
            first_sentence = re.split(r'(?<=[.!?])\s+', cleaned)[0]
            title = first_sentence[:100]

        tt = TextTeaser()
        sentences = tt.summarize(title, cleaned)
        return "\n".join(f"• {s}" for s in sentences[:num_sentences])
    except Exception as e:
        print(f"[!] TextTeaser lỗi: {e}")
        return ""


# ─── KẾT HỢP TẤT CẢ (VOTING) ─────────────────────────────────────────────────

def voting_summary(text: str, num_sentences: int = 3) -> str:
    """
    Kết hợp LSA + TextRank + TextTeaser + KeyBERT bằng weighted voting:
    - LSA:        weight 2
    - TextRank:   weight 2
    - TextTeaser: weight 3
    - KeyBERT:    weight 4 (cao nhất - dựa trên semantic similarity)
    Câu được nhiều thuật toán chọn AND chứa từ khoá quan trọng → ưu tiên nhất.
    """
    _ensure_nltk()
    cleaned = clean_ocr_text(text)
    votes = {}
    all_sentences = []

    # ── LSA + TextRank votes ──
    try:
        from sumy.parsers.plaintext import PlaintextParser
        from sumy.nlp.tokenizers import Tokenizer
        from sumy.summarizers.lsa import LsaSummarizer
        from sumy.summarizers.text_rank import TextRankSummarizer
        from sumy.nlp.stemmers import Stemmer
        from sumy.utils import get_stop_words

        parser = PlaintextParser.from_string(cleaned, Tokenizer("english"))
        stemmer = Stemmer("english")
        stop_words = get_stop_words("english")
        all_sentences = [str(s) for s in parser.document.sentences]

        lsa = LsaSummarizer(stemmer)
        lsa.stop_words = stop_words
        for s in lsa(parser.document, num_sentences):
            votes[str(s)] = votes.get(str(s), 0) + 2

        tr = TextRankSummarizer(stemmer)
        tr.stop_words = stop_words
        for s in tr(parser.document, num_sentences):
            votes[str(s)] = votes.get(str(s), 0) + 2
    except Exception:
        pass

    # ── TextTeaser votes ──
    try:
        from textteaser_lib import TextTeaser
        first = re.split(r'(?<=[.!?])\s+', cleaned)[0][:100]
        tt = TextTeaser()
        for s in tt.summarize(first, cleaned)[:num_sentences]:
            votes[s] = votes.get(s, 0) + 3
    except Exception:
        pass

    # ── KeyBERT votes (bonus score dựa trên từ khoá) ──
    try:
        keywords = extract_keywords(cleaned, top_n=15)
        if keywords and all_sentences:
            for s in all_sentences:
                kw_score = _score_sentence_by_keywords(s, keywords)
                if kw_score > 0:
                    # Cộng KeyBERT score * 4 (weight cao nhất)
                    votes[s] = votes.get(s, 0) + kw_score * 4
    except Exception:
        pass

    if not votes:
        return topic_sentence_summary(text, num_sentences)

    # Chọn top N theo tổng điểm
    top = sorted(votes.items(), key=lambda x: -x[1])[:num_sentences]
    top_set = set(s for s, _ in top)

    # Giữ thứ tự xuất hiện trong văn bản gốc
    try:
        ordered = [s for s in all_sentences if s in top_set]
    except Exception:
        ordered = [s for s, _ in top]

    return "\n".join(f"• {s}" for s in ordered)


def summarize(
    text: str,
    api_key: str = "",
    num_sentences: int = 3,
    language: str = "English"
) -> dict:
    print("[*] Đang trích xuất topic sentences...")
    topics = topic_sentence_summary(text, num_sentences)

    print("[*] Đang load KeyBERT & trích xuất từ khoá...")
    keywords = extract_keywords(text, top_n=15)
    keywords_str = "\n".join(f"• {kw}" for kw in keywords) if keywords else "(không có)"

    print("[*] Đang chạy LSA + KeyBERT rerank...")
    lsa = lsa_summary(text, num_sentences)

    print("[*] Đang chạy TextRank + KeyBERT rerank...")
    tr = textrank_summary(text, num_sentences)

    print("[*] Đang chạy KeyBERT thuần...")
    kb = keybert_summary(text, num_sentences)

    print("[*] Đang chạy TextTeaser...")
    tt = textteaser_summary(text, num_sentences=num_sentences)

    print("[*] Đang voting LSA + TextRank + TextTeaser + KeyBERT...")
    voting = voting_summary(text, num_sentences)

    abs_result = ""
    if api_key:
        print("[*] Đang tóm tắt bằng Gemini AI...")
        abs_result = abstractive_summary(text, api_key, language)
    else:
        print("[!] Không có API key → bỏ qua Gemini")

    return {
        "topics":    topics,
        "keywords":  keywords_str,   # ← từ khoá KeyBERT trích xuất
        "keybert":   kb,             # ← tóm tắt thuần KeyBERT
        "lsa":       lsa,            # ← LSA + KeyBERT rerank
        "textrank":  tr,             # ← TextRank + KeyBERT rerank
        "textteaser":tt,
        "voting":    voting,         # ← tất cả + KeyBERT, tốt nhất
        "abstractive": abs_result,
    }


def summarize_file(
    file_path: str,
    api_key: str = "",
    lang_ocr: str = "en",
    num_sentences: int = 3,
    language: str = "English"
) -> dict:
    """
    Scan file + tóm tắt trong 1 bước.

    Ví dụ:
        from summarizer import summarize_file
        result = summarize_file(r"G:\\essay.pdf", api_key="AIza...", lang_ocr="en")
        print(result["topics"])
        print(result["combined"])
        print(result["abstractive"])
    """
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    from Paddle_ocr_scanner import quick_scan

    print(f"[*] Đang scan: {file_path}")
    text = quick_scan(file_path, lang=lang_ocr)

    if not text.strip():
        return {"topics": "", "lsa": "", "textrank": "", "combined": "",
                "abstractive": "", "error": "Không tìm thấy nội dung"}

    print(f"[✓] Scan xong: {len(text)} ký tự")
    result = summarize(text, api_key=api_key,
                       num_sentences=num_sentences, language=language)
    result["raw_text"] = text
    result["cleaned_text"] = clean_ocr_text(text)
    return result