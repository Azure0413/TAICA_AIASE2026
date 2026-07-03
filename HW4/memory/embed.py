"""Embedding 後端：本地 sentence-transformers（預設）或 LAN 上 Ollama（選用）。

設計準則：
- 模型只在第一次取得時載入（lazy），避免拖慢 import 與 CLI 冷啟動。
- 結果向量做 L2 normalize，後續 cosine similarity 等同 dot product。
- 純函式介面 `embed_texts(list[str]) -> np.ndarray`，
  確保 hybrid 排序在固定模型下 100% 可重現。
- 可由環境變數 `PI_EMBED_BACKEND` 切換（"st"=sentence-transformers, "ollama"=remote）。
- 模型權重在第一次跑時自下載；之後完全離線運作，不打雲端 API。
"""
from __future__ import annotations
import os
import threading
from typing import Optional

import numpy as np


_DEFAULT_ST_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_DEFAULT_OLLAMA_MODEL = "bge-m3"
_DEFAULT_OLLAMA_URL = "http://192.168.63.184:11434"

_lock = threading.Lock()
_st_model = None
_st_model_name: Optional[str] = None


def _l2_normalize(arr: np.ndarray) -> np.ndarray:
    if arr.ndim == 1:
        norm = np.linalg.norm(arr)
        return arr if norm == 0 else arr / norm
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def _backend() -> str:
    return os.environ.get("PI_EMBED_BACKEND", "st").lower()


def _st_model_id() -> str:
    return os.environ.get("PI_EMBED_MODEL", _DEFAULT_ST_MODEL)


def _ollama_model_id() -> str:
    return os.environ.get("PI_EMBED_MODEL", _DEFAULT_OLLAMA_MODEL)


def _ollama_base_url() -> str:
    return os.environ.get("PI_OLLAMA_URL", _DEFAULT_OLLAMA_URL).rstrip("/")


def _get_st_model():
    global _st_model, _st_model_name
    name = _st_model_id()
    with _lock:
        if _st_model is not None and _st_model_name == name:
            return _st_model
        from sentence_transformers import SentenceTransformer
        _st_model = SentenceTransformer(name)
        _st_model_name = name
        return _st_model


def _embed_st(texts: list[str]) -> np.ndarray:
    model = _get_st_model()
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vecs, dtype=np.float32)


def _embed_ollama(texts: list[str]) -> np.ndarray:
    import requests
    url = f"{_ollama_base_url()}/api/embeddings"
    model = _ollama_model_id()
    vecs = []
    for t in texts:
        r = requests.post(url, json={"model": model, "prompt": t}, timeout=60)
        r.raise_for_status()
        vecs.append(r.json()["embedding"])
    arr = np.asarray(vecs, dtype=np.float32)
    return _l2_normalize(arr)


def embed_texts(texts: list[str]) -> np.ndarray:
    """把一批文字編成 L2-normalize 過的向量。
    回傳 shape 為 (len(texts), dim) 的 float32 numpy array。
    """
    if not texts:
        return np.zeros((0, 1), dtype=np.float32)
    backend = _backend()
    if backend == "ollama":
        return _embed_ollama(texts)
    return _embed_st(texts)


def cosine_scores(query_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
    """query 已 normalize、doc 也 normalize 時，cos sim == dot product。
    回傳 shape (n_docs,) 的分數，落在 [-1, 1]。
    """
    if doc_vecs.shape[0] == 0:
        return np.zeros((0,), dtype=np.float32)
    return doc_vecs @ query_vec
