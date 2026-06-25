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


# ─── B1: UNDERTHESEA — TÁCH TỪ TIẾNG VIỆT ────────────────────────────────────

def segment_vi(text: str) -> str:
    """Tách từ tiếng Việt bằng underthesea (cài: pip install underthesea)."""
    try:
        from underthesea import word_tokenize
        return word_tokenize(text, format="text")
    except ImportError:
        return text
    except Exception as e:
        print(f"[!] underthesea lỗi: {e}")
        return text


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

_keybert_models = {}   # cache theo tên model

def _get_keybert(multilingual: bool = False):
    """Lazy load KeyBERT. multilingual=True dùng model đa ngôn ngữ (cho tiếng Việt),
    nếu tải lỗi sẽ tự lùi về model mặc định."""
    name = ("paraphrase-multilingual-MiniLM-L12-v2" if multilingual
            else "all-MiniLM-L6-v2")
    if name not in _keybert_models:
        try:
            from keybert import KeyBERT
            print(f"[*] Đang load KeyBERT model: {name} ...")
            _keybert_models[name] = KeyBERT(model=name)
            print("[✓] KeyBERT sẵn sàng")
        except ImportError:
            print("[!] Cần cài: pip install keybert sentence-transformers")
            _keybert_models[name] = None
        except Exception as e:
            print(f"[!] Không load được {name} ({e}); dùng model mặc định...")
            if multilingual:
                return _get_keybert(multilingual=False)
            _keybert_models[name] = None
    return _keybert_models[name]


# Stopword tiếng Việt (hư từ) — lọc khỏi danh sách từ khoá
_VI_STOPWORDS = {
    "và","là","của","có","các","những","được","trên","trong","cho","với","để",
    "khi","này","đó","một","người","không","đã","sẽ","đang","rằng","thì","mà",
    "ở","ra","vào","lên","xuống","nên","cũng","vẫn","còn","nếu","vì","do","bởi",
    "tại","theo","như","hay","hoặc","nhưng","tuy","tuy_nhiên","bị","rất","quá",
    "lại","đến","từ","về","qua","sau","trước","giữa","cùng","nhau","kia","ấy",
    "nào","gì","ai","sao","đâu","bao","nhiều","ít","mỗi","mọi","tất","tất_cả",
    "cả","chỉ","thêm","nữa","đều","luôn","việc","cái","con","chiếc","sự","điều",
    "thế","vậy","nó","họ","tôi","bạn","chúng","ta","anh","chị","em","ông","bà",
    "đây","bằng","này","đó","một_số","khác",
}


def extract_keywords(text: str, top_n: int = 10, lang: str = "en") -> list[str]:
    """
    Trích xuất từ khoá quan trọng bằng KeyBERT.
    - lang="vi": tách từ bằng underthesea + lọc stopword tiếng Việt và dùng
      model đa ngôn ngữ → từ khoá là cụm có nghĩa ("tìm kiếm") thay vì syllable lẻ.
    - lang khác (mặc định "en"): dùng stopword tiếng Anh như cũ.
    Trả về list từ khoá theo thứ tự quan trọng giảm dần.
    """
    is_vi = str(lang).lower().startswith("vi")
    kb = _get_keybert(multilingual=is_vi)
    if not kb:
        return []
    try:
        cleaned = clean_ocr_text(text)
        if is_vi:
            doc = segment_vi(cleaned)          # "tìm kiếm" -> "tìm_kiếm"
            stop_words = list(_VI_STOPWORDS)
        else:
            doc = cleaned
            stop_words = "english"

        raw = kb.extract_keywords(
            doc,
            keyphrase_ngram_range=(1, 2),      # unigram + bigram
            stop_words=stop_words,
            use_mmr=True,                       # đa dạng, tránh trùng lặp
            diversity=0.5,
            top_n=top_n * 2 if is_vi else top_n,  # lấy dư để lọc bớt hư từ
        )

        out = []
        for kw, _score in raw:
            phrase = kw.replace("_", " ").strip()   # bỏ gạch nối của underthesea
            toks = [t for t in re.split(r"[ _]+", phrase.lower()) if t]
            if len(phrase) < 2:
                continue
            # bỏ cụm chỉ gồm toàn hư từ tiếng Việt
            if toks and all(t in _VI_STOPWORDS for t in toks):
                continue
            if phrase not in out:
                out.append(phrase)
            if len(out) >= top_n:
                break
        return out
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


# ─── SINH CÂU HỎI TỰ ĐỘNG (Question Generation) ──────────────────────────────

def _qg_split_sentences(text: str) -> list[str]:
    """Tách câu sạch để sinh câu hỏi (bỏ bullet, câu quá ngắn, trùng lặp)."""
    cleaned = clean_ocr_text(text)
    raw = re.split(r'(?<=[.!?])\s+|\n+', cleaned)
    sents = []
    for s in raw:
        s = s.strip().lstrip("•-*–").strip()
        if len(s.split()) >= 4 and s not in sents:
            sents.append(s)
    return sents


def _qg_find_context(keyword: str, sentences: list[str]) -> str:
    """Tìm câu gốc đầu tiên chứa từ khoá (làm đáp án / câu khoét)."""
    kw = keyword.lower()
    for s in sentences:
        if kw in s.lower():
            return s
    return ""


def generate_questions(text: str, keywords: list, max_def: int = 6,
                       max_cloze: int = 6) -> list[dict]:
    """
    Sinh câu hỏi RULE-BASED (template + ngữ pháp, Mitkov & Ha 2003):
      - 'definition' : định nghĩa-trong-ngữ-cảnh — đáp án là câu gốc chứa từ khoá.
      - 'cloze'      : điền khuyết — khoét từ khoá khỏi câu, đáp án là từ khoá.
    Trả về list dict {qtype, front, back, hint}. Deterministic, không cần API.
    """
    sentences = _qg_split_sentences(text)
    if not sentences:
        return []

    cards, used_cloze = [], set()

    # 1) Định nghĩa trong ngữ cảnh — đáp án thực thay vì để rỗng
    n_def = 0
    for kw in keywords:
        if n_def >= max_def:
            break
        ctx = _qg_find_context(kw, sentences)
        if not ctx:
            continue
        cards.append({
            "qtype": "definition",
            "front": f"'{kw}' nghĩa là gì / liên quan gì trong tài liệu?",
            "back":  ctx,
            "hint":  "",
        })
        n_def += 1

    # 2) Điền khuyết (cloze) — kỹ thuật QG kinh điển
    n_cloze = 0
    for kw in keywords:
        if n_cloze >= max_cloze:
            break
        ctx = _qg_find_context(kw, sentences)
        if not ctx or ctx in used_cloze:
            continue
        # Chỉ khoét khi từ khoá đứng độc lập (có ranh giới từ), tránh khoét
        # nhầm bên trong một từ dài hơn (vd 'lp' trong 'help').
        pattern = r"(?<!\w)" + re.escape(kw) + r"(?!\w)"
        blank = re.sub(pattern, "_____", ctx, count=1, flags=re.IGNORECASE)
        if blank == ctx:        # từ khoá không đứng độc lập -> bỏ
            continue
        used_cloze.add(ctx)
        cards.append({
            "qtype": "cloze",
            "front": f"Điền vào chỗ trống:\n\n{blank}",
            "back":  kw,
            "hint":  f"{len(kw)} ký tự, bắt đầu bằng '{kw[:1].upper()}'",
        })
        n_cloze += 1

    return cards


def generate_questions_ai(text: str, api_key: str, language: str = "Vietnamese",
                          n: int = 5) -> list[dict]:
    """
    Sinh câu hỏi TRANSFORMER-BASED qua Gemini (Lopez et al. 2021) — tùy chọn.
    Trả về list dict {qtype:'ai', front, back, hint}. Không key/lỗi -> [].
    """
    if not api_key:
        return []
    prompt = (
        f"Dựa vào đoạn văn dưới đây, hãy tạo {n} câu hỏi ôn tập bằng {language} "
        f"kèm câu trả lời ngắn gọn. Mỗi câu hỏi nằm trên MỘT dòng, đúng định dạng:\n"
        f"Q: <câu hỏi> || A: <câu trả lời>\n\n"
        f"ĐOẠN VĂN:\n{clean_ocr_text(text)[:4000]}\n"
    )
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.0-flash", contents=prompt)
        raw = resp.text or ""
    except Exception as e:
        print(f"[!] Gemini QG lỗi: {e}")
        return []

    cards = []
    for line in raw.splitlines():
        if "||" not in line or "Q:" not in line:
            continue
        q, _, a = line.partition("||")
        q = q.split("Q:", 1)[-1].strip()
        a = a.split("A:", 1)[-1].strip()
        if q and a:
            cards.append({"qtype": "ai", "front": q, "back": a, "hint": ""})
    return cards


# ─── B2: RAKE-NLTK — TRÍCH XUẤT TỪ KHOÁ ─────────────────────────────────────

def rake_keywords(text: str, top_n: int = 10) -> list:
    """Trích xuất từ khoá bằng RAKE-NLTK (cài: pip install rake-nltk)."""
    try:
        from rake_nltk import Rake
        _ensure_nltk()
        r = Rake()
        r.extract_keywords_from_text(clean_ocr_text(text))
        phrases = r.get_ranked_phrases()
        return phrases[:top_n]
    except ImportError:
        print("[!] Cần cài: pip install rake-nltk")
        return []
    except Exception as e:
        print(f"[!] RAKE lỗi: {e}")
        return []


# ─── B3: NETWORKX TEXTRANK ────────────────────────────────────────────────────

def networkx_textrank_summary(text: str, num_sentences: int = 3) -> str:
    """
    TextRank thuần dựa trên NetworkX PageRank + TF-IDF cosine similarity.
    Cài: pip install networkx scikit-learn numpy
    """
    _ensure_nltk()
    cleaned = clean_ocr_text(text)
    try:
        import numpy as np
        import networkx as nx
        from sklearn.metrics.pairwise import cosine_similarity
        from sklearn.feature_extraction.text import TfidfVectorizer

        sentences = re.split(r'(?<=[.!?])\s+', cleaned)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

        if len(sentences) < 2:
            return "\n".join(f"• {s}" for s in sentences[:num_sentences])

        vectorizer = TfidfVectorizer(stop_words="english")
        tfidf_matrix = vectorizer.fit_transform(sentences)
        sim_matrix = cosine_similarity(tfidf_matrix)
        np.fill_diagonal(sim_matrix, 0)

        graph = nx.from_numpy_array(sim_matrix)
        scores = nx.pagerank(graph, max_iter=200)

        ranked = sorted(scores.items(), key=lambda x: -x[1])[:num_sentences]
        ranked_indices = sorted(i for i, _ in ranked)
        return "\n".join(f"• {sentences[i]}" for i in ranked_indices)

    except ImportError as e:
        print(f"[!] NetworkX TextRank cần: pip install networkx scikit-learn numpy ({e})")
        return textrank_summary(text, num_sentences)
    except Exception as e:
        print(f"[!] NetworkX TextRank lỗi: {e}")
        return ""


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


# ─── SO SÁNH PHƯƠNG PHÁP TÓM TẮT (reference-free) ────────────────────────────

def _summary_metrics(summary: str, original_chars: int, keywords: list):
    """Chỉ số không cần bản tham chiếu: số câu, số ký tự, tỉ lệ nén, độ phủ từ khoá."""
    content = " ".join(
        l.strip().lstrip("•-*–").strip()
        for l in (summary or "").splitlines() if l.strip())
    sents = [s for s in re.split(r'(?<=[.!?])\s+', content) if s.strip()]
    n_sent = len(sents)
    n_char = len(content)
    compress = round(n_char / original_chars * 100, 1) if original_chars else 0.0
    coverage = 0.0
    if keywords and content:
        low = content.lower()
        hit = sum(1 for k in keywords if str(k).lower() in low)
        coverage = round(hit / len(keywords) * 100)
    return n_sent, n_char, compress, coverage


def compare_summaries(text: str, num_sentences: int = 3, api_key: str = "",
                      lang: str = "en", keywords: list = None) -> list:
    """
    Chạy nhiều phương pháp tóm tắt trên cùng một văn bản và đo chỉ số so sánh.
    Trả về list dict: {key, name, kind, summary, n_sent, n_char, compress,
                       coverage, seconds, error}. Mỗi phương pháp bọc try/except.
    """
    cleaned = clean_ocr_text(text)
    original_chars = len(cleaned)
    if keywords is None:
        try:
            keywords = extract_keywords(text, top_n=12, lang=lang)
        except Exception:
            keywords = []

    methods = [
        ("networkx_textrank", "NetworkX TextRank", "extractive",
            lambda t, n: networkx_textrank_summary(t, n)),
        ("textrank", "TextRank (sumy)", "extractive",
            lambda t, n: textrank_summary(t, n)),
        ("lsa", "LSA", "extractive",
            lambda t, n: lsa_summary(t, n)),
        ("textteaser", "TextTeaser", "extractive",
            lambda t, n: textteaser_summary(t, num_sentences=n)),
        ("keybert", "KeyBERT", "extractive",
            lambda t, n: keybert_summary(t, n)),
        ("voting", "Voting Ensemble", "extractive",
            lambda t, n: voting_summary(t, n)),
    ]

    results = []
    for key, name, kind, fn in methods:
        t0 = time.perf_counter()
        try:
            summ = fn(text, num_sentences) or ""
            err = ""
        except Exception as e:
            summ, err = "", str(e)
        secs = round(time.perf_counter() - t0, 2)
        n_sent, n_char, compress, coverage = _summary_metrics(
            summ, original_chars, keywords)
        results.append({
            "key": key, "name": name, "kind": kind, "summary": summ,
            "n_sent": n_sent, "n_char": n_char, "compress": compress,
            "coverage": coverage, "seconds": secs, "error": err,
        })

    # Gemini (abstractive) — chỉ chạy khi có API key
    if api_key:
        t0 = time.perf_counter()
        language = "Vietnamese" if str(lang).lower().startswith("vi") else "English"
        try:
            summ = abstractive_summary(text, api_key, language) or ""
            err = summ if summ.startswith("[!]") else ""
            if err:
                summ = ""
        except Exception as e:
            summ, err = "", str(e)
        secs = round(time.perf_counter() - t0, 2)
        n_sent, n_char, compress, coverage = _summary_metrics(
            summ, original_chars, keywords)
        results.append({
            "key": "abstractive", "name": "Gemini (abstractive)",
            "kind": "abstractive", "summary": summ, "n_sent": n_sent,
            "n_char": n_char, "compress": compress, "coverage": coverage,
            "seconds": secs, "error": err,
        })

    return results


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

    print("[*] Đang trích xuất từ khoá bằng RAKE...")
    rake_kws = rake_keywords(text, top_n=10)
    rake_str = "\n".join(f"• {kw}" for kw in rake_kws) if rake_kws else ""

    print("[*] Đang chạy LSA + KeyBERT rerank...")
    lsa = lsa_summary(text, num_sentences)

    print("[*] Đang chạy TextRank + KeyBERT rerank...")
    tr = textrank_summary(text, num_sentences)

    print("[*] Đang chạy NetworkX TextRank...")
    nx_tr = networkx_textrank_summary(text, num_sentences)

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
        "topics":            topics,
        "keywords":          keywords_str,
        "rake_keywords":     rake_str,
        "keybert":           kb,
        "lsa":               lsa,
        "textrank":          tr,
        "networkx_textrank": nx_tr,
        "textteaser":        tt,
        "voting":            voting,
        "abstractive":       abs_result,
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