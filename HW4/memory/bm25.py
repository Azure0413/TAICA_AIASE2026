"""BM25-lite：給每筆文件對查詢打相關度分數，回傳排序後的前 K 筆。整個作業的核心。

實作為標準 Okapi BM25（Robertson/Sparck-Jones, "Okapi at TREC-3", 1995）：
  score(q,d) = Σ_qi IDF(qi) · (tf·(k1+1)) / (tf + k1·(1 - b + b·|d|/avgdl))
  IDF(qi)    = ln( (N - n + 0.5)/(n + 0.5) + 1 )

設計上保持「確定性、單一純函式」：相同輸入永遠回相同結果，不呼叫外部模型或 RNG。
這是隱藏測試與 benchmark 的契約；任務二的 hybrid 路徑放在獨立函式 (hybrid.py::hybrid_search)。
"""
from __future__ import annotations
import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    """小寫化後，取出英數字詞與單個 CJK 字元。不做 stemming。（已提供）"""
    return _TOKEN_RE.findall(text.lower())


def bm25_search(
    query: str,
    docs: list[dict],
    k: int = 8,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[dict]:
    """標準 BM25 排序。

    Args:
        query: 查詢字串。
        docs:  [{"id": str, "text": str}, ...]
        k:     回傳前 k 筆。
        k1, b: BM25 參數（預設 k1=1.5, b=0.75）。

    Returns:
        [{"id": str, "score": float}, ...]，分數高到低；同分時保持原始輸入順序。
    """
    if not docs:
        return []

    tokenized: list[list[str]] = [tokenize(d["text"]) for d in docs]
    doc_lens: list[int] = [len(t) for t in tokenized]
    n_docs = len(docs)
    avgdl = (sum(doc_lens) / n_docs) if n_docs > 0 else 0.0

    q_terms = tokenize(query)
    if not q_terms:
        topn = min(k, n_docs)
        return [{"id": docs[i]["id"], "score": 0.0} for i in range(topn)]

    unique_q = set(q_terms)
    df: dict[str, int] = {}
    for tokens in tokenized:
        for term in set(tokens) & unique_q:
            df[term] = df.get(term, 0) + 1

    idf: dict[str, float] = {
        term: math.log(((n_docs - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5)) + 1.0)
        for term in unique_q
    }

    scored: list[tuple[int, float]] = []
    for i, tokens in enumerate(tokenized):
        if not tokens:
            scored.append((i, 0.0))
            continue
        tf_counts = Counter(tokens)
        dl = doc_lens[i]
        norm = (1.0 - b + b * (dl / avgdl)) if avgdl > 0 else 1.0
        score = 0.0
        for term in q_terms:
            tf = tf_counts.get(term, 0)
            if tf == 0:
                continue
            score += idf[term] * (tf * (k1 + 1.0)) / (tf + k1 * norm)
        scored.append((i, score))

    scored.sort(key=lambda x: (-x[1], x[0]))
    top = scored[:k]
    return [{"id": docs[i]["id"], "score": s} for i, s in top]
