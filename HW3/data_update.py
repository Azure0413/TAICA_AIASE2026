#!/usr/bin/env python3
"""
data_update.py — 資料收集、清理、Chunking、Embedding 與向量索引腳本

功能：
  - 讀取 data/raw/ 中的原始檔案（支援 .pdf, .md, .txt）
  - 清理文字並儲存至 data/processed/
  - 切分為適合 embedding 的片段（段落優先 + 固定長度 + overlap）
  - 使用 sentence-transformers 本地模型產生向量
  - 將 chunk 文字、向量、metadata 寫入 ChromaDB
  - 支援 --rebuild 全量重建與增量更新（SHA256 hash 判斷）
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── 路徑設定 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
HASH_FILE = BASE_DIR / "data" / ".file_hashes.json"

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "80"))
COLLECTION_NAME = "image_restoration_kb"


def _resolve_chroma_path() -> str:
    """
    解析 ChromaDB 儲存路徑。
    hnswlib（C++ 底層）在 Windows 上無法處理非 ASCII 路徑（如含中文的目錄），
    若偵測到此問題，自動改用 ~/.cache/image_restoration_chroma 作為替代路徑。
    """
    raw = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    # 轉為絕對路徑
    resolved = str((BASE_DIR / raw).resolve()) if not os.path.isabs(raw) else raw
    try:
        resolved.encode("ascii")
        return resolved
    except UnicodeEncodeError:
        # 路徑含非 ASCII 字元（如中文），改用 home 目錄下的 ASCII 路徑
        fallback = str(Path.home() / ".cache" / "image_restoration_chroma")
        print(f"[WARN] ChromaDB 路徑含非 ASCII 字元，改用備用路徑: {fallback}")
        return fallback


CHROMA_PERSIST_DIR = _resolve_chroma_path()


# ═══════════════════════════════════════════════════════════
#  工具函式
# ═══════════════════════════════════════════════════════════

def compute_file_hash(filepath: Path) -> str:
    """計算檔案的 SHA256 hash"""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            sha256.update(block)
    return sha256.hexdigest()


def load_hash_registry() -> dict:
    if HASH_FILE.exists():
        with open(HASH_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_hash_registry(registry: dict) -> None:
    with open(HASH_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════
#  文字提取
# ═══════════════════════════════════════════════════════════

def extract_text_from_pdf(filepath: Path) -> str:
    """從 PDF 提取文字（使用 PyMuPDF）"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("[ERROR] 請安裝 PyMuPDF: pip install PyMuPDF")
        sys.exit(1)

    doc = fitz.open(str(filepath))
    text_parts = []
    for page in doc:
        text = page.get_text("text")
        if text.strip():
            text_parts.append(text)
    doc.close()
    return "\n\n".join(text_parts)


def extract_text_from_md(filepath: Path) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def extract_text_from_txt(filepath: Path) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


EXTRACTORS = {
    ".pdf": extract_text_from_pdf,
    ".md": extract_text_from_md,
    ".txt": extract_text_from_txt,
}


# ═══════════════════════════════════════════════════════════
#  文字清理（針對學術論文優化）
# ═══════════════════════════════════════════════════════════

def clean_text(text: str) -> str:
    """
    清理學術論文文字：
    - 移除 HTML 標籤
    - 合併被 PDF 換行截斷的句子（行末無句號的短行）
    - 移除頁碼、頁首頁尾
    - 移除多餘空白
    - 移除 arXiv 標頭雜訊
    """
    # 移除 HTML 標籤
    text = re.sub(r"<[^>]+>", "", text)

    # 移除 arXiv 標頭（如 arXiv:1234.56789v1 [cs.CV] ...）
    text = re.sub(r"arXiv:\d+\.\d+v?\d*\s*\[[\w.]+\]\s*\d+\s*\w+\s*\d+", "", text)

    # 移除純頁碼行
    text = re.sub(r"\n\s*\d{1,3}\s*\n", "\n", text)

    # 合併被 PDF 換行截斷的行（行末不是句號/冒號/標題符號的短行）
    lines = text.split("\n")
    merged_lines = []
    buffer = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if buffer:
                merged_lines.append(buffer)
                buffer = ""
            merged_lines.append("")
            continue

        if buffer:
            # 如果上一行末尾不是句末標點，且當前行不像是新段落/標題開頭
            if (buffer and buffer[-1] not in ".!?:;。！？" 
                and not re.match(r"^(#{1,6}\s|Abstract|Introduction|Conclusion|References|\d+\.\s|Table\s|Figure\s|Fig\.)", stripped)
                and len(stripped) > 5):
                buffer = buffer + " " + stripped
            else:
                merged_lines.append(buffer)
                buffer = stripped
        else:
            buffer = stripped

    if buffer:
        merged_lines.append(buffer)

    text = "\n".join(merged_lines)

    # 移除連續空行（保留最多一個）
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 移除多餘空格（保留換行）
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()


# ═══════════════════════════════════════════════════════════
#  Chunking（段落優先 + 固定長度 + overlap）
# ═══════════════════════════════════════════════════════════

def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """
    段落優先切分策略：
    1. 先依段落（雙換行）拆分
    2. 合併短段落直到接近 chunk_size
    3. 過長段落依句子邊界拆分
    4. 相鄰 chunks 保留 overlap
    """
    paragraphs = re.split(r"\n\n+", text)
    paragraphs = [p.strip() for p in paragraphs if p.strip() and len(p.strip()) > 10]

    # Phase 1: 合併短段落 / 拆分過長段落
    raw_chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n\n{para}".strip() if current else para
        else:
            if current:
                raw_chunks.append(current)

            if len(para) > chunk_size:
                # 依句子拆分過長段落
                sentences = re.split(r"(?<=[.!?])\s+", para)
                sub = ""
                for sent in sentences:
                    if len(sub) + len(sent) + 1 <= chunk_size:
                        sub = f"{sub} {sent}".strip() if sub else sent
                    else:
                        if sub:
                            raw_chunks.append(sub)
                        # 如果單句超長，強制切割
                        if len(sent) > chunk_size:
                            for i in range(0, len(sent), chunk_size - overlap):
                                raw_chunks.append(sent[i:i + chunk_size])
                            sub = ""
                        else:
                            sub = sent
                current = sub
            else:
                current = para

    if current:
        raw_chunks.append(current)

    # Phase 2: 加入 overlap
    if overlap > 0 and len(raw_chunks) > 1:
        overlapped = [raw_chunks[0]]
        for i in range(1, len(raw_chunks)):
            prev_tail = raw_chunks[i - 1][-overlap:]
            overlapped.append(f"{prev_tail} {raw_chunks[i]}")
        return overlapped

    return raw_chunks


# ═══════════════════════════════════════════════════════════
#  Embedding（sentence-transformers 本地模型）
# ═══════════════════════════════════════════════════════════

_embed_model = None


def get_embedding_model():
    global _embed_model
    if _embed_model is not None:
        return _embed_model

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("[ERROR] 請安裝 sentence-transformers: pip install sentence-transformers")
        sys.exit(1)

    print(f"[INFO] 載入 Embedding 模型: {EMBEDDING_MODEL}")
    _embed_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embed_model


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=32)
    return embeddings.tolist()


# ═══════════════════════════════════════════════════════════
#  ChromaDB 操作
# ═══════════════════════════════════════════════════════════

def get_chroma_client():
    try:
        import chromadb
    except ImportError:
        print("[ERROR] 請安裝 chromadb: pip install chromadb")
        sys.exit(1)

    persist_dir = str(BASE_DIR / CHROMA_PERSIST_DIR)
    return chromadb.PersistentClient(path=persist_dir)


def rebuild_collection(client) -> None:
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"[INFO] 已刪除舊 collection: {COLLECTION_NAME}")
    except Exception:
        pass


def upsert_chunks(client, chunks, embeddings, metadatas, ids) -> None:
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    batch = 100
    for i in range(0, len(chunks), batch):
        end = min(i + batch, len(chunks))
        collection.upsert(
            ids=ids[i:end],
            documents=chunks[i:end],
            embeddings=embeddings[i:end],
            metadatas=metadatas[i:end],
        )
    print(f"[INFO] 已寫入 {len(chunks)} 個 chunks 到 ChromaDB")


def remove_file_chunks(client, source_file: str) -> None:
    try:
        collection = client.get_or_create_collection(name=COLLECTION_NAME)
        results = collection.get(where={"source": source_file})
        if results["ids"]:
            collection.delete(ids=results["ids"])
            print(f"[INFO] 已移除 {len(results['ids'])} 個舊 chunks: {source_file}")
    except Exception as e:
        print(f"[WARN] 移除舊 chunks 時發生錯誤: {e}")


# ═══════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════

def get_raw_files() -> list[Path]:
    supported = set(EXTRACTORS.keys())
    files = []
    for f in sorted(RAW_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in supported:
            files.append(f)
    return files


def process_file(filepath: Path) -> str:
    ext = filepath.suffix.lower()
    extractor = EXTRACTORS.get(ext)
    if not extractor:
        print(f"[WARN] 不支援的檔案格式: {filepath}")
        return ""

    print(f"[INFO] 處理檔案: {filepath.name}")
    raw_text = extractor(filepath)
    cleaned = clean_text(raw_text)

    # 儲存到 processed/  (原始檔名去掉副檔名 + .txt)
    out_name = filepath.stem + ".txt"
    out_path = PROCESSED_DIR / out_name
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(cleaned)
    print(f"[INFO] 已儲存清理後文字: {out_path.name} ({len(cleaned)} 字元)")
    return cleaned


def run_update(rebuild: bool = False) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    raw_files = get_raw_files()
    if not raw_files:
        print("[WARN] data/raw/ 中沒有找到任何支援的檔案（.pdf, .md, .txt）")
        return

    print(f"[INFO] 找到 {len(raw_files)} 個原始檔案")

    # Hash 紀錄
    hash_registry = {} if rebuild else load_hash_registry()

    files_to_update = []
    for f in raw_files:
        current_hash = compute_file_hash(f)
        if rebuild or hash_registry.get(f.name) != current_hash:
            files_to_update.append((f, current_hash))
        else:
            print(f"[SKIP] 檔案未變動: {f.name}")

    if not files_to_update and not rebuild:
        print("[INFO] 所有檔案皆為最新，無需更新")
        return

    # ChromaDB
    client = get_chroma_client()

    if rebuild:
        print("[INFO] 執行全量重建 (--rebuild)")
        for p in PROCESSED_DIR.glob("*.txt"):
            p.unlink()
        rebuild_collection(client)
        hash_registry = {}

    # Embedding 模型（只載入一次）
    print("[INFO] 準備 Embedding 模型...")
    _ = get_embedding_model()

    all_chunks, all_embeddings, all_metadatas, all_ids = [], [], [], []
    new_registry = dict(hash_registry)

    for filepath, file_hash in files_to_update:
        if not rebuild:
            remove_file_chunks(client, filepath.name)

        cleaned_text = process_file(filepath)
        if not cleaned_text:
            continue

        chunks = chunk_text(cleaned_text)
        print(f"[INFO] 切分為 {len(chunks)} 個 chunks")

        embeddings = embed_texts(chunks)

        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            chunk_id = f"{filepath.stem}_chunk_{idx:04d}"
            metadata = {
                "source": filepath.name,
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "file_type": filepath.suffix.lower(),
            }
            all_chunks.append(chunk)
            all_embeddings.append(emb)
            all_metadatas.append(metadata)
            all_ids.append(chunk_id)

        new_registry[filepath.name] = file_hash

    if all_chunks:
        upsert_chunks(client, all_chunks, all_embeddings, all_metadatas, all_ids)

    save_hash_registry(new_registry)

    collection = client.get_or_create_collection(name=COLLECTION_NAME)
    total = collection.count()

    # 強制觸發 HNSW 索引初始化與持久化（ChromaDB 0.6.x 需要 query 才會寫入 .bin 檔）
    if total > 0 and all_embeddings:
        try:
            sample_emb = all_embeddings[0] if all_embeddings else embed_texts(["test"])[0]
            collection.query(query_embeddings=[sample_emb], n_results=1)
            print("[INFO] HNSW 索引驗證通過，已持久化至磁碟")
        except Exception as e:
            print(f"[WARN] HNSW 索引驗證失敗: {e}")

    print(f"\n{'='*50}")
    print(f"[DONE] 更新完成！")
    print(f"  處理檔案數: {len(files_to_update)}")
    print(f"  新增 chunks: {len(all_chunks)}")
    print(f"  Vector DB 總 chunks: {total}")
    print(f"{'='*50}")


# ═══════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Image Restoration RAG — 資料收集、清理、Chunking、Embedding 與向量索引",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python data_update.py               # 增量更新（僅處理有變動的檔案）
  python data_update.py --rebuild     # 全量重建（清空並重新索引所有資料）

支援格式: .pdf, .md, .txt
資料目錄:
  data/raw/        原始資料
  data/processed/  清理後的純文字檔案
        """,
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="全量重建：清空 data/processed/ 與 Vector DB，重新處理所有檔案",
    )
    args = parser.parse_args()
    run_update(rebuild=args.rebuild)


if __name__ == "__main__":
    main()
