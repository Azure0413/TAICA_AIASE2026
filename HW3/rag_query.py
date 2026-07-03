#!/usr/bin/env python3
"""
rag_query.py — RAG 問答 CLI 介面

流程: Embed Query → ChromaDB Retrieve top-k → 組裝 Prompt → LiteLLM (OpenAI 相容) → 含引用來源回答
支援互動式模式（保留 3 輪對話歷史）與單次查詢模式
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── 設定 ──────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")


def _resolve_chroma_path() -> str:
    raw = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    resolved = str((BASE_DIR / raw).resolve()) if not os.path.isabs(raw) else raw
    try:
        resolved.encode("ascii")
        return resolved
    except UnicodeEncodeError:
        fallback = str(Path.home() / ".cache" / "image_restoration_chroma")
        print(f"[WARN] ChromaDB 路徑含非 ASCII 字元，改用備用路徑: {fallback}")
        return fallback


CHROMA_PERSIST_DIR = _resolve_chroma_path()
TOP_K = int(os.getenv("TOP_K", "5"))
DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "gemini-2.5-flash")
COLLECTION_NAME = "image_restoration_kb"

LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "")
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "")

# ── System Prompt ─────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert research assistant specializing in Image Restoration (denoising, super-resolution, deblurring, deraining, dehazing, all-in-one restoration, face restoration, and diffusion-based restoration).

You answer questions based ONLY on the provided retrieved context from a curated knowledge base of image restoration research papers.

Rules:
1. Base your answer strictly on the provided context. If the context is insufficient, say so.
2. ALWAYS cite sources using the format [Source: <filename>, Chunk #<N>] after each key claim.
3. Be precise and technical when discussing architectures, loss functions, training strategies, and evaluation metrics.
4. If the user writes in Chinese, respond in Chinese. If in English, respond in English.
5. When comparing methods, clearly state each method's strengths and limitations with citations.
"""


# ── Embedding ─────────────────────────────────────────────
_embed_model = None


def get_embedding_model():
    global _embed_model
    if _embed_model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            print("[ERROR] 請安裝 sentence-transformers: pip install sentence-transformers")
            sys.exit(1)
        _embed_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embed_model


def embed_query(query: str) -> list[float]:
    model = get_embedding_model()
    return model.encode(query).tolist()


# ── ChromaDB 查詢 ─────────────────────────────────────────
def get_chroma_collection():
    try:
        import chromadb
    except ImportError:
        print("[ERROR] 請安裝 chromadb: pip install chromadb")
        sys.exit(1)

    persist_dir = str(BASE_DIR / CHROMA_PERSIST_DIR)
    client = chromadb.PersistentClient(path=persist_dir)
    try:
        return client.get_collection(name=COLLECTION_NAME)
    except Exception:
        print("[ERROR] 找不到 Vector DB collection。請先執行: python data_update.py --rebuild")
        sys.exit(1)


def retrieve_chunks(query: str, top_k: int = TOP_K) -> list[dict]:
    collection = get_chroma_collection()
    query_embedding = embed_query(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    for i in range(len(results["ids"][0])):
        chunks.append({
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        })
    return chunks


# ── Prompt 組裝 ───────────────────────────────────────────
def build_context_prompt(query: str, chunks: list[dict]) -> str:
    context_parts = []
    for i, chunk in enumerate(chunks):
        source = chunk["metadata"].get("source", "unknown")
        chunk_idx = chunk["metadata"].get("chunk_index", "?")
        context_parts.append(
            f"--- [Context {i+1}] Source: {source}, Chunk #{chunk_idx} ---\n{chunk['text']}"
        )

    context_str = "\n\n".join(context_parts)

    return f"""Based on the following retrieved context from image restoration research papers, answer the user's question.
Always cite sources using [Source: filename, Chunk #N] format.

=== Retrieved Context ===
{context_str}

=== User Question ===
{query}
"""


# ── LLM 呼叫（透過 OpenAI 相容介面連接 LiteLLM）────────────
def call_llm(messages: list[dict], model: str = DEFAULT_LLM_MODEL) -> str:
    try:
        import openai
    except ImportError:
        print("[ERROR] 請安裝 openai: pip install openai")
        sys.exit(1)

    if not LITELLM_API_KEY:
        print("[ERROR] 未設定 LITELLM_API_KEY。")
        print("  請執行: cp .env.example .env")
        print("  然後在 .env 中填入助教提供的 API Key")
        sys.exit(1)

    client = openai.OpenAI(
        api_key=LITELLM_API_KEY,
        base_url=LITELLM_BASE_URL,
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[ERROR] LLM 呼叫失敗: {e}"


# ── RAG 問答 ──────────────────────────────────────────────
def rag_answer(
    query: str,
    top_k: int = TOP_K,
    model: str = DEFAULT_LLM_MODEL,
    conversation_history: list[dict] | None = None,
) -> tuple[str, list[dict]]:
    """完整 RAG 流程：Embed → Retrieve → Generate"""
    chunks = retrieve_chunks(query, top_k=top_k)
    if not chunks:
        return "找不到相關的知識片段。請確認 Vector DB 中已有資料（執行 data_update.py --rebuild）。", []

    context_prompt = build_context_prompt(query, chunks)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if conversation_history:
        messages.extend(conversation_history[-(3 * 2):])  # 最近 3 輪
    messages.append({"role": "user", "content": context_prompt})

    answer = call_llm(messages, model=model)
    return answer, chunks


def display_answer(answer: str, chunks: list[dict]) -> None:
    print("\n" + "=" * 60)
    print("📝 Answer:")
    print("=" * 60)
    print(answer)
    print("\n" + "-" * 60)
    print("📚 Retrieved Sources:")
    print("-" * 60)
    for i, chunk in enumerate(chunks):
        source = chunk["metadata"].get("source", "unknown")
        chunk_idx = chunk["metadata"].get("chunk_index", "?")
        distance = chunk.get("distance", 0)
        similarity = max(0, 1 - distance)
        print(f"  [{i+1}] {source} (Chunk #{chunk_idx}) — similarity: {similarity:.4f}")
    print()


# ── CLI ───────────────────────────────────────────────────
def interactive_mode(top_k: int, model: str) -> None:
    print("=" * 60)
    print("🔍 Image Restoration RAG — 互動式問答")
    print(f"   Model: {model} | Top-K: {top_k}")
    print("   輸入 quit / exit 結束對話")
    print("=" * 60)

    history: list[dict] = []

    while True:
        try:
            query = input("\n❓ Question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Bye!")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            print("👋 Bye!")
            break

        answer, chunks = rag_answer(query, top_k=top_k, model=model, conversation_history=history)
        display_answer(answer, chunks)

        history.append({"role": "user", "content": query})
        history.append({"role": "assistant", "content": answer})


def single_query_mode(query: str, top_k: int, model: str) -> None:
    answer, chunks = rag_answer(query, top_k=top_k, model=model)
    display_answer(answer, chunks)


def main():
    parser = argparse.ArgumentParser(
        description="Image Restoration RAG — 知識問答 CLI 介面",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python rag_query.py                                        # 互動式模式
  python rag_query.py --query "What is DnCNN?"               # 單次查詢
  python rag_query.py --query "比較 SwinIR 和 Restormer"      # 中文查詢
  python rag_query.py --query "..." --top-k 10               # 增加檢索數量
  python rag_query.py --query "..." --model gpt-oss:20b      # 切換模型

前置條件:
  1. 已執行 python data_update.py --rebuild 建立向量索引
  2. .env 中已填入 LITELLM_API_KEY
        """,
    )
    parser.add_argument("--query", "-q", type=str, default=None,
                        help="單次查詢問題，未提供則進入互動式模式")
    parser.add_argument("--top-k", "-k", type=int, default=TOP_K,
                        help=f"檢索 top-k chunks（預設: {TOP_K}）")
    parser.add_argument("--model", "-m", type=str, default=DEFAULT_LLM_MODEL,
                        help=f"LLM 模型名稱（預設: {DEFAULT_LLM_MODEL}）")
    args = parser.parse_args()

    if args.query:
        single_query_mode(args.query, args.top_k, args.model)
    else:
        interactive_mode(args.top_k, args.model)


if __name__ == "__main__":
    main()
