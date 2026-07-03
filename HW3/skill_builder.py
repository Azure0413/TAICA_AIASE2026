#!/usr/bin/env python3
"""
skill_builder.py — 自動從 RAG 知識庫生成 skill.md Agent 技能文件

流程：
  1. 對知識庫發出多個探索性問題
  2. 收集並去重 RAG 返回的相關 chunks
  3. 呼叫 LLM 彙整成符合 Agent Skill 格式的 skill.md
"""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── 設定 ──────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "gemini-2.5-flash")
COLLECTION_NAME = "image_restoration_kb"
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "")
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "")

# 探索性問題：涵蓋知識庫的各個面向
EXPLORATION_QUERIES = [
    "What are the main image restoration tasks: super-resolution, denoising, deblurring, deraining, dehazing?",
    "What are the key CNN-based architectures for image restoration such as DnCNN, EDSR, RCAN, RDN, FFDNet?",
    "What are the Transformer-based methods for image restoration: SwinIR, Restormer, Uformer, IPT, MambaIR?",
    "How do diffusion models and score-based methods work for image restoration SR3, ResShift, IR-SDE?",
    "What are GAN-based super-resolution methods SRGAN ESRGAN and their perceptual quality improvements?",
    "What are all-in-one universal image restoration methods PromptIR OneRestore AutoDIR RestoreAgent?",
    "What benchmark datasets evaluation metrics PSNR SSIM LPIPS are used in image restoration?",
    "What are the key training strategies loss functions perceptual loss adversarial loss in image restoration?",
    "What are the main challenges and limitations in real-world image restoration blind restoration?",
    "What plug-and-play methods and model-based approaches exist for image restoration?",
]

# skill.md 生成 Prompt
SKILL_SYNTHESIS_PROMPT = """You are a research knowledge synthesizer. Based on the retrieved context from an image restoration research paper knowledge base, write a comprehensive skill.md document that an AI Agent can use as a reference.

The document must follow EXACTLY this structure and include ALL sections:

---
# Skill: Image Restoration Research Knowledge Base

## Metadata
- **知識領域**: Image Restoration（超解析度、去噪、去模糊、去雨、去霧、全能修復、擴散模型修復）
- **資料來源數量**: 30 份研究論文
- **最後更新時間**: {today}
- **適用 Agent 類型**: 研究助理 / 技術顧問 / 論文問答機器人

## Overview
[Write 150-200 words describing the scope of this knowledge base: what image restoration tasks are covered, what era of research (CNN → GAN → Transformer → Diffusion), and what types of questions this skill can answer]

## Core Concepts
[List 12-15 key concepts with 1-2 sentence explanations each. Cover: PSNR/SSIM metrics, residual learning, perceptual loss, attention mechanisms, Transformer architecture for restoration, diffusion model score matching, blind/non-blind restoration, all-in-one frameworks, plug-and-play priors, benchmark datasets]

## Key Trends
[List 6-8 major research trends observed in the papers: e.g., shift from CNN to Transformer, rise of diffusion models, all-in-one restoration, real-world degradation modeling, Mamba-based methods]

## Key Entities
### Key Authors & Institutions
[List prominent researchers and their affiliated institutions from the papers]

### Key Models & Methods
[List all major model names: DnCNN, FFDNet, SRGAN, ESRGAN, EDSR, RCAN, RDN, IPT, SwinIR, Restormer, Uformer, MIRNet, MPRNet, HINet, NAFNet/SIMD, MAXIM, MambaIR, SR3, ResShift, IR-SDE, PromptIR, OneRestore, AutoDIR, RestoreAgent, PlugPlay, SeeSR, SUPIR]

### Key Datasets
[List benchmark datasets: BSD68, Set5/Set14, Urban100, DIV2K, SIDD, GoPro, RESIDE, RainDrop, etc.]

## Methodology & Best Practices
[Describe 5-7 established methodologies and best practices in image restoration research, with brief explanations of why they work]

## Knowledge Gaps & Limitations
[Describe 4-5 current limitations of this skill/knowledge base: paper cutoff date, missing sub-topics, language bias, etc.]

## Example Q&A
[Provide exactly 5 representative Q&A pairs that demonstrate what this skill can answer. Use actual knowledge from the context.]

Q1: What is the key innovation of SwinIR over previous CNN-based image restoration methods?
A1: [Answer based on context]

Q2: How does ResShift achieve efficient diffusion-based image restoration?
A2: [Answer based on context]

Q3: What makes PromptIR different from single-task image restoration models?
A3: [Answer based on context]

Q4: What evaluation metrics are most commonly used in super-resolution research and what do they measure?
A4: [Answer based on context]

Q5: How do plug-and-play methods differ from end-to-end deep learning approaches for image restoration?
A5: [Answer based on context]

## Source References
| 文件名稱 | 類型 | 主要貢獻 |
|---|---|---|
[List all 30 papers from the knowledge base with their main contribution in one line each]
---

Fill in ALL sections with accurate, detailed content derived from the provided context. Do not leave any section empty or with placeholder text.
"""


# ── Embedding ──────────────────────────────────────────────
_embed_model = None


def get_embedding_model():
    global _embed_model
    if _embed_model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            print("[ERROR] 請安裝: pip install sentence-transformers")
            sys.exit(1)
        print(f"[INFO] 載入 Embedding 模型: {EMBEDDING_MODEL}")
        _embed_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embed_model


def embed_query(query: str) -> list[float]:
    return get_embedding_model().encode(query).tolist()


# ── ChromaDB ───────────────────────────────────────────────
def get_chroma_collection():
    try:
        import chromadb
    except ImportError:
        print("[ERROR] 請安裝: pip install chromadb")
        sys.exit(1)

    persist_dir = str(BASE_DIR / CHROMA_PERSIST_DIR)
    client = chromadb.PersistentClient(path=persist_dir)
    try:
        return client.get_collection(name=COLLECTION_NAME)
    except Exception:
        print("[ERROR] 找不到 Vector DB。請先執行: python data_update.py --rebuild")
        sys.exit(1)


def retrieve_chunks(query: str, top_k: int = 5) -> list[dict]:
    collection = get_chroma_collection()
    query_emb = embed_query(query)
    results = collection.query(
        query_embeddings=[query_emb],
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


# ── LLM 呼叫 ──────────────────────────────────────────────
def call_llm(messages: list[dict], model: str) -> str:
    try:
        import openai
    except ImportError:
        print("[ERROR] 請安裝: pip install openai")
        sys.exit(1)

    if not LITELLM_API_KEY:
        print("[ERROR] 未設定 LITELLM_API_KEY，請在 .env 中填入助教提供的 API Key")
        sys.exit(1)

    client = openai.OpenAI(
        api_key=LITELLM_API_KEY,
        base_url=LITELLM_BASE_URL,
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            max_tokens=4096,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] LLM 呼叫失敗: {e}")
        sys.exit(1)


# ── 知識探索 ──────────────────────────────────────────────
def explore_knowledge_base(top_k_per_query: int = 5) -> tuple[str, set[str]]:
    """
    發出多個探索問題，收集並去重 chunks，
    回傳 (彙整後的 context 字串, 所有出現的來源檔案集合)
    """
    print(f"[INFO] 開始探索知識庫（共 {len(EXPLORATION_QUERIES)} 個問題，每題 top-{top_k_per_query}）")

    seen_ids: set[str] = set()
    all_chunks: list[dict] = []

    for i, query in enumerate(EXPLORATION_QUERIES, 1):
        print(f"[INFO] ({i}/{len(EXPLORATION_QUERIES)}) {query[:70]}...")
        chunks = retrieve_chunks(query, top_k=top_k_per_query)
        for chunk in chunks:
            if chunk["id"] not in seen_ids:
                seen_ids.add(chunk["id"])
                all_chunks.append(chunk)

    # 依相似度排序，取前 40 個最相關 chunks
    all_chunks.sort(key=lambda c: c["distance"])
    selected = all_chunks[:40]

    # 收集來源
    sources: set[str] = set()
    for chunk in selected:
        src = chunk["metadata"].get("source", "")
        if src:
            sources.add(src)

    # 組裝 context
    parts = []
    for chunk in selected:
        src = chunk["metadata"].get("source", "unknown")
        idx = chunk["metadata"].get("chunk_index", "?")
        parts.append(f"[Source: {src}, Chunk #{idx}]\n{chunk['text']}")

    context_str = "\n\n---\n\n".join(parts)
    print(f"[INFO] 收集到 {len(selected)} 個去重後的 chunks，涵蓋 {len(sources)} 篇論文")
    return context_str, sources


# ── skill.md 生成 ──────────────────────────────────────────
def build_skill_md(model: str, output_path: Path) -> None:
    context_str, sources = explore_knowledge_base(top_k_per_query=5)
    today = date.today().isoformat()

    user_content = (
        SKILL_SYNTHESIS_PROMPT.format(today=today)
        + "\n\n=== RETRIEVED CONTEXT FROM KNOWLEDGE BASE ===\n\n"
        + context_str
    )

    print(f"[INFO] 正在呼叫 LLM ({model}) 生成 skill.md...")
    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert in image restoration research and AI knowledge management. "
                "Write comprehensive, accurate, and well-structured technical documentation."
            ),
        },
        {"role": "user", "content": user_content},
    ]

    skill_content = call_llm(messages, model=model)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(skill_content)

    print(f"\n{'='*60}")
    print(f"[DONE] skill.md 已生成！")
    print(f"  輸出路徑: {output_path}")
    print(f"  檔案大小: {len(skill_content)} 字元")
    print(f"  涵蓋論文: {len(sources)} 篇")
    print(f"{'='*60}")


# ── CLI ────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Image Restoration RAG — 自動生成 skill.md Agent 技能文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python skill_builder.py                          # 生成 skill.md（預設輸出）
  python skill_builder.py --output skill.md        # 指定輸出路徑
  python skill_builder.py --model gemini-2.5-flash # 指定 LLM 模型

前置條件:
  1. 已執行 python data_update.py --rebuild 建立向量索引
  2. .env 中已填入 LITELLM_API_KEY
        """,
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="skill.md",
        help="輸出 skill.md 的路徑（預設: skill.md）",
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default=DEFAULT_LLM_MODEL,
        help=f"LLM 模型名稱（預設: {DEFAULT_LLM_MODEL}）",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = BASE_DIR / output_path

    build_skill_md(model=args.model, output_path=output_path)


if __name__ == "__main__":
    main()
