#!/usr/bin/env bash
# Demo D3 (cross-session multi-preference injection) - pure Python repro，
# 不需要起 Pi runtime；展示「Session A 寫的記憶，Session B 在另一個 process 拿得回」。
#
# 用法：
#   bash demo/run_demo_d3.sh
#
# 觀察重點：
# 1) 第一次 inject 是空的（沒記憶）
# 2) 連寫五筆後，第二次 inject 把相關記憶塞進 budget 內
# 3) 把 .json 檔 cat 出來，可以看到 SHA-256 id 去重 + 完整持久化

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DEMO_STORE="$(mktemp -t pi-memory-demo.XXXXXX.json)"
export PI_MEMORY_PATH="$DEMO_STORE"
trap 'rm -f "$DEMO_STORE"' EXIT

PYBIN="${PYTHON:-python3}"

echo "═══════════════ Demo D3: 跨 session 多項偏好注入 ═══════════════"
echo "暫存記憶檔: $DEMO_STORE"
echo

echo "── [Session A — 空狀態] ─────────────────────────────────────"
echo "問題: 「我要 commit 改動，需要做什麼？」"
echo "注入內容:"
PYTHONPATH=. "$PYBIN" -m memory.cli inject --query "我要 commit 改動，需要做什麼" --budget 2000
echo
echo "（空白 → 沒記憶可注入；agent 會反問使用者）"
echo

echo "── [Session A — 使用者陸續告訴 agent 五件事] ───────────────"
for line in \
  "這專案用 pnpm，不要用 npm。測試指令是 pnpm test。|build" \
  "commit 訊息一律用中文撰寫，code 註解可以用英文。|convention" \
  "Python 程式碼用 ruff 與 black 做 lint / format，送 PR 前要先跑過。|convention,build" \
  "部署到 Fly.io；staging 是另一個 app。|deploy" \
  "主分支受保護，必須開 PR 且至少一人核可才能合併。|convention,git"; do
  summary="${line%%|*}"
  tags="${line##*|}"
  PYTHONPATH=. "$PYBIN" -m memory.cli capture --summary "$summary" --tags "$tags"
done
echo

echo "── [Session B — 另一個 process / 重新開機後] ───────────────"
echo "問題: 「我要 commit 改動然後 deploy，整個流程要做哪些事？」"
echo "注入內容:"
PYTHONPATH=. "$PYBIN" -m memory.cli inject --query "我要 commit 改動然後 deploy，整個流程要做哪些事" --budget 2000
echo

echo "── [硬碟內容檢查] ───────────────────────────────────────────"
echo "$(ls -la "$DEMO_STORE")"
echo
"$PYBIN" -c "
import json
with open('$DEMO_STORE') as f:
    data = json.load(f)
print(f'共 {len(data)} 筆記憶（每筆都有唯一 SHA-256 id）：')
for i, o in enumerate(data, 1):
    print(f'  {i}. {o[\"id\"][:10]}…  {o[\"summary\"][:50]}')
"
echo
echo "✓ 跨 session 持久化驗證完成。"
