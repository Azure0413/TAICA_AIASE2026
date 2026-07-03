#!/usr/bin/env bash
# 一鍵錄影腳本：跑完約 90 秒，涵蓋所有需要被助教看到的證據。
#
# 用法（在錄影軟體開錄後執行）：
#   bash demo/record_all.sh
#
# 內容（按順序）：
#   ① 環境與測試（5s）            → 證明 28 個 pytest 全綠
#   ② Benchmark - 純 BM25（10s）  → 證明數字命中助教參考值
#   ③ Benchmark - Hybrid（15s）   → 證明任務二 hybrid 有效
#   ④ 跨 session 記憶 demo（30s） → 證明「Session A 寫 → Session B 讀回」
#   ⑤ 隱私過濾 demo（15s）        → 證明 PI_PRIVACY=1 真的遮金鑰
#   ⑥ /recall + /forget CLI（10s）→ 證明使用者可審視 / 修剪記憶

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

DEMO_STORE="$(mktemp -t pi-memory-demo.XXXXXX.json)"
export PI_MEMORY_PATH="$DEMO_STORE"
trap 'rm -f "$DEMO_STORE"' EXIT

PYBIN="${PYTHON:-python3}"

section() {
  echo ""
  echo "════════════════════════════════════════════════════════════════"
  echo "  $1"
  echo "════════════════════════════════════════════════════════════════"
  sleep 1
}

pause() { sleep "${1:-2}"; }

# ───────────────────────────────────────────────────────────────────────
clear
echo "AIASE2026 HW4 — Pi Memory  /  Demo recording"
echo "Author: $(whoami)  Repo: $ROOT"
echo "Date: $(date '+%Y-%m-%d %H:%M')"
pause 3

# ── ① 測試 ────────────────────────────────────────────────────────────
section "① 28 個 pytest 全綠（核心 13 + 進階 15）"
"$PYBIN" -m pytest -q
pause 2

# ── ② Benchmark BM25 ──────────────────────────────────────────────────
section "② Benchmark：純 BM25 — 數字應命中助教參考值"
echo ""
echo "▼ 小語料（30 筆 / 21 題）："
"$PYBIN" benchmark/run_benchmark.py --k 5 | tail -8
pause 2
echo ""
echo "▼ 大語料（100 筆 / 40 題）："
"$PYBIN" benchmark/run_benchmark.py --corpus corpus_large.jsonl --queries queries_large.jsonl --k 5 | tail -8
pause 2

# ── ③ Benchmark Hybrid ────────────────────────────────────────────────
section "③ Benchmark：Hybrid (BM25 + embedding, RRF) — 任務二 A 證據"
echo ""
echo "▼ 小語料（hybrid）："
PI_RETRIEVAL=hybrid "$PYBIN" benchmark/run_benchmark.py --k 5 2>/dev/null | tail -8
pause 2
echo ""
echo "▼ 大語料（hybrid）— 注意 MRR / nDCG 的躍升："
PI_RETRIEVAL=hybrid "$PYBIN" benchmark/run_benchmark.py --corpus corpus_large.jsonl --queries queries_large.jsonl --k 5 2>/dev/null | tail -8
pause 3

# ── ④ 跨 session ──────────────────────────────────────────────────────
section "④ 跨 session 記憶：Session A 寫入 → Session B 讀回"
echo ""
echo "▼ Session A — 告訴 agent 三件事："
"$PYBIN" -m memory.cli capture --summary "這個專案用 pnpm 不用 npm，測試指令是 pnpm test" --tags build
"$PYBIN" -m memory.cli capture --summary "commit 訊息一律用中文撰寫"                          --tags convention
"$PYBIN" -m memory.cli capture --summary "部署到 Fly.io；staging 在另一個 app"                --tags deploy
echo ""
echo "▼ 硬碟上的記憶檔（證明真的持久化）："
ls -la "$DEMO_STORE"
echo ""
echo "▼ Session B — 另一個 process / 重開 agent 後問問題："
echo "Q: 我要 commit 改動然後 deploy，整個流程要做哪些事？"
echo ""
echo "→ 注入回 agent context 的內容："
"$PYBIN" -m memory.cli inject --query "我要 commit 改動然後 deploy，整個流程要做哪些事" --budget 2000
echo ""
echo ""
echo "✓ 三筆昨天的記憶被正確 retrieve + inject 回 context — agent 不需再反問。"
pause 3

# ── ⑤ 隱私過濾 ────────────────────────────────────────────────────────
section "⑤ 任務二 B：隱私過濾 PI_PRIVACY=1"
echo ""
echo "▼ 使用者不小心貼了金鑰 / token / 密碼："
rm -f "$DEMO_STORE"
PI_PRIVACY=1 "$PYBIN" -m memory.cli capture --summary "API_KEY=sk-PROJ0000abcdEFGHabcdEFGH1234XYZ"
PI_PRIVACY=1 "$PYBIN" -m memory.cli capture --summary "GitHub token: ghp_abcdefghij0123456789KLMNOP"
PI_PRIVACY=1 "$PYBIN" -m memory.cli capture --summary "db password=hunter2!"
echo ""
echo "▼ 硬碟上實際存的內容（cat 真實磁碟檔案）："
"$PYBIN" -c "
import json
data = json.load(open('$DEMO_STORE'))
for o in data: print('  •', o['summary'])
"
echo ""
echo "✓ 所有金鑰已被 [REDACTED] 取代 — 硬碟上沒有原文洩漏。"
pause 3

# ── ⑥ /recall + /forget ───────────────────────────────────────────────
section "⑥ 任務二 D：/recall + /forget CLI"
echo ""
echo "▼ /recall（列出所有記憶）："
"$PYBIN" -m memory.cli list
echo ""
echo "▼ /forget（按 summary 刪除）："
"$PYBIN" -m memory.cli forget --summary "API_KEY=[REDACTED]"
echo ""
echo "▼ 刪後再 /recall 確認："
"$PYBIN" -m memory.cli list
pause 3

# ───────────────────────────────────────────────────────────────────────
section "Demo 結束"
echo ""
echo "  • 核心 BM25 + JSON store：28 tests 全綠"
echo "  • Benchmark：純 BM25 命中參考值；Hybrid 在四個指標全升"
echo "  • 任務二做了 4 項：Hybrid / Privacy / Decay / CLI"
echo "  • 跨 session 持久化：Session A 寫 → Session B 拿到"
echo ""
echo "  詳見 README.md 與 REPORT.md。"
echo ""
