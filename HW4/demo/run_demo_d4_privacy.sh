#!/usr/bin/env bash
# Demo D4 — 隱私過濾（PI_PRIVACY=1）
# 展示：即使使用者把 API key / GitHub token 貼進對話，落地到硬碟前已被遮蔽。

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DEMO_STORE="$(mktemp -t pi-memory-demo.XXXXXX.json)"
export PI_MEMORY_PATH="$DEMO_STORE"
export PI_PRIVACY=1
trap 'rm -f "$DEMO_STORE"' EXIT

PYBIN="${PYTHON:-python3}"

echo "═══════════════ Demo D4: 隱私過濾 ═══════════════"
echo "啟用：PI_PRIVACY=1"
echo "暫存記憶檔: $DEMO_STORE"
echo

echo "── 使用者不小心把金鑰 / 密碼貼進對話 ──"
PYTHONPATH=. "$PYBIN" -m memory.cli capture --summary "請記下：OpenAI API_KEY=sk-PROJ0000abcdEFGHabcdEFGH1234XYZ" --tags secret
PYTHONPATH=. "$PYBIN" -m memory.cli capture --summary "GitHub token 是 ghp_abcdefghij0123456789KLMNOPqrst1234" --tags secret
PYTHONPATH=. "$PYBIN" -m memory.cli capture --summary "production db password=hunter2! 暫時記著" --tags secret
PYTHONPATH=. "$PYBIN" -m memory.cli capture --summary "Auth header: Bearer eyJhbGciOiJIUzI1NiJ9.PAYLOADPAYLOAD.SIGNATURE" --tags secret
echo

echo "── 直接 cat 硬碟內容，確認金鑰確實已被遮蔽 ──"
echo "──────────────────────────────────────────────────"
"$PYBIN" -c "
import json
with open('$DEMO_STORE') as f:
    data = json.load(f)
for o in data:
    print('  •', o['summary'])
    assert 'PROJ0000abcdEFGH' not in o['summary'], 'LEAK!'
    assert 'abcdefghij0123456789KL' not in o['summary'], 'LEAK!'
    assert 'hunter2' not in o['summary'], 'LEAK!'
    assert 'PAYLOADPAYLOAD' not in o['summary'], 'LEAK!'
print()
print('✓ 所有金鑰 / 密碼 / token 已被 [REDACTED] 取代，magnetic 硬碟上沒有任何原文洩漏。')
"
