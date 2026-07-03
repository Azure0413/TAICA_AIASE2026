"""Hybrid retrieval：BM25（lexical）+ embedding（semantic），用 RRF 融合。

為什麼選 RRF（Reciprocal Rank Fusion, Cormack 2009）：
- 不需校正不同分數的尺度（BM25 是非負無上界，cosine 在 [-1,1]）。
- 只看「排名」，對任一單一通道的離群分數魯棒。
- 一個超參 `rrf_k`（預設 60，原論文與多個 IR 系統實作通用值）。

設計上完全與 `bm25.py::bm25_search` 解耦：
- `bm25_search` 保持純 BM25、確定性、不引入任何外部依賴。
- 本檔可選擇性啟用；若未安裝 embedding 後端，會優雅退回純 BM25。
"""
from __future__ import annotations
import os
from typing import Optional

from .bm25 import bm25_search


def _rrf_fuse(rankings: list[list[str]], rrf_k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion. rankings 為每個檢索器吐出的 id 清單（前面 = 較相關）。"""
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (rrf_k + rank)
    return fused


def _bm25_only(query: str, docs: list[dict], k: int) -> list[dict]:
    return bm25_search(query, docs, k=k)


def hybrid_search(
    query: str,
    docs: list[dict],
    k: int = 8,
    rrf_k: int = 60,
    pool: int = 50,
    bm25_only: bool = False,
) -> list[dict]:
    """Hybrid 排序：BM25 + embedding 用 RRF 融合，回傳前 k 筆。

    Args:
        query:   查詢。
        docs:    [{"id": str, "text": str}, ...]
        k:       回傳前 k 筆。
        rrf_k:   RRF 平滑常數（預設 60，原論文 / Elasticsearch / Vespa 通用值）。
        pool:    兩個檢索器各自取前多少筆來融合（>= k）。
        bm25_only: True 時退回純 BM25（為了測試方便、或 embedding 後端壞了）。

    Returns:
        [{"id": str, "score": float}, ...]
    """
    if not docs:
        return []
    if bm25_only:
        return _bm25_only(query, docs, k)

    pool = max(pool, k)

    bm25_ranked = bm25_search(query, docs, k=pool)
    bm25_ids = [r["id"] for r in bm25_ranked]

    try:
        from .embed import embed_texts, cosine_scores
        import numpy as np
        texts = [d["text"] for d in docs]
        doc_vecs = embed_texts(texts)
        q_vec = embed_texts([query])[0]
        scores = cosine_scores(q_vec, doc_vecs)
        order = list(np.argsort(-scores))
        sem_ranked_ids = [docs[i]["id"] for i in order[:pool]]
    except Exception:
        return bm25_ranked[:k]

    fused = _rrf_fuse([bm25_ids, sem_ranked_ids], rrf_k=rrf_k)
    id_to_pos = {d["id"]: i for i, d in enumerate(docs)}

    ranked = sorted(
        fused.items(),
        key=lambda x: (-x[1], id_to_pos.get(x[0], 1 << 30)),
    )
    return [{"id": doc_id, "score": score} for doc_id, score in ranked[:k]]


def enabled_by_env() -> bool:
    """從環境變數判斷是否要走 hybrid（給 core.retrieve 使用）。"""
    val = os.environ.get("PI_RETRIEVAL", "bm25").lower()
    return val == "hybrid"
