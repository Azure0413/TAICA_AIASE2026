#!/usr/bin/env bash
# Demo D2 — 跨語言記憶（中文存、英文撈）
# 展示：純 BM25 在中英文間零字面交集 → 接不到；
#       hybrid (BM25 + multilingual MiniLM + RRF) → 接到。
# 要先 pip install sentence-transformers（在 requirements.txt 內）。

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DEMO_STORE="$(mktemp -t pi-memory-demo.XXXXXX.json)"
export PI_MEMORY_PATH="$DEMO_STORE"
trap 'rm -f "$DEMO_STORE"' EXIT

PYBIN="${PYTHON:-python3}"

echo "═══════════════ Demo D2: 跨語言記憶 ═══════════════"
echo "暫存記憶檔: $DEMO_STORE"
echo

echo "── [Session A — 中文寫入] ──"
PYTHONPATH=. "$PYBIN" -m memory.cli capture --summary "我們的資料庫用 PostgreSQL，向量索引用 pgvector" --tags db,arch
PYTHONPATH=. "$PYBIN" -m memory.cli capture --summary "週會固定在每週二早上十點，開會前要更新 PROGRESS.md" --tags people,process
PYTHONPATH=. "$PYBIN" -m memory.cli capture --summary "資料庫 migration 一律用 alembic 管理，不要手動修改 schema" --tags db,convention
echo

echo "── [Session B — 英文查詢，純 BM25] ──"
echo "Q: what database do we use, and how do we store embeddings?"
echo "  → BM25 結果："
PYTHONPATH=. "$PYBIN" -m memory.cli retrieve --query "what database do we use, and how do we store embeddings?" --k 3 | "$PYBIN" -m json.tool
echo

echo "── [Session B — 英文查詢，開啟 hybrid] ──"
echo "Q: what database do we use, and how do we store embeddings?"
echo "  → Hybrid 結果："
PYTHONPATH=. PI_RETRIEVAL=hybrid "$PYBIN" -m memory.cli retrieve --query "what database do we use, and how do we store embeddings?" --k 3 | "$PYBIN" -m json.tool
echo

echo "── [Inject 後實際送進 LLM 的文字] ──"
PYTHONPATH=. PI_RETRIEVAL=hybrid "$PYBIN" -m memory.cli inject --query "what database do we use, and how do we store embeddings?"
echo
echo
echo "✓ Hybrid 把中文「資料庫用 PostgreSQL，向量索引用 pgvector」對到了英文查詢。"
