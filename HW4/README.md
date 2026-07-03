# AIASE2026 HW4 — Pi Memory（Python）

> 為本地 coding agent ([Pi](https://github.com/earendil-works/pi)) 打造跨 session 的持久記憶：
> **capture → store → retrieve → inject**。
> 核心、benchmark、評分皆為 Python；Pi 端只有薄 TS bridge（已提供，不需修改）。

> **🎬 Demo 影片**：https://youtu.be/F7HbVZuHJ7Q （≈ 90 秒，一鍵跑完所有展示）
> **📂 對照截圖**：見 [`demo/`](demo/) 資料夾的 `01-tests…` ~ `06-demo-summary.png`

---

## 1. 系統設計概述（30 秒版）

| 層 | 模組 | 職責 |
|---|---|---|
| **存儲** | `memory/store.py` | JSON 持久層，SHA-256 id 去重，atomic write（`.tmp` + `os.replace`） |
| **排序（核心、確定性）** | `memory/bm25.py::bm25_search` | 標準 Okapi BM25（`k1=1.5, b=0.75`），純函式，**100% 可重現** |
| **排序（進階、選用）** | `memory/hybrid.py::hybrid_search` | BM25 + embedding，**RRF (Cormack 2009)** 融合 |
| **遺忘** | `memory/decay.py` | 指數衰減 `exp(-ln2·age/half_life)`，命中時 touch `last_used_at` |
| **隱私** | `memory/privacy.py` | regex 遮蔽 `sk-…`、`ghp_…`、`Bearer …`、`password=…` |
| **整合** | `memory/core.py` | 公開 API（`capture / retrieve / build_injection / list_all / forget`），用環境變數 toggle 進階功能，**預設行為 = 純 BM25**（隱藏單元測試契約） |
| **CLI** | `memory/cli.py` | 給 Pi bridge 呼叫；也支援 `list` / `forget` 供 `/recall` `/forget` 命令 |
| **Bridge** | `pi-bridge/extension.ts` | Pi extension：`before_agent_start` 注入、`remember` 工具、`/recall` `/forget` 命令 |

「**確定性外殼包住機率性核心**」的具體實踐 ── 預設 retrieve = BM25 = 確定性。
hybrid 排序、embedding、decay touch 為**選擇性外殼**，由環境變數啟用，不污染預設路徑。

---

## 2. 環境

| 項目 | 值 |
|---|---|
| Python | **3.13.5**（assignment 要求 `>= 3.10`） |
| 對話 LLM | `qwen2.5:7b`（或 `gpt-oss:20b`），跑在 **LAN 內自架 Ollama**（`http://192.168.63.184:11434`） |
| 後端 | Ollama（remote，OpenAI-compatible `/v1` endpoint，pi-ai 直接接） |
| Context size | 32K（Qwen 2.5 預設） |
| 寄宿硬體 | LAN 內自架伺服器（具備 GPU，VRAM 充足以執行所選 7B/20B 模型） |
| Embedding（任務二 hybrid） | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，**本機 Python process 內 CPU 推論**；模型權重首次執行從 Hugging Face 下載並快取於 `~/.cache/huggingface/`，之後**完全離線**。可用 `PI_EMBED_BACKEND=ollama` 切換成 LAN 上 `bge-m3`（也是離線的） |

> **資料流分離**：
> - 記憶 JSON 寫硬碟 = **本機**（執行 Pi 的開發機，路徑由 `PI_MEMORY_PATH` 控制，預設 `~/.pi-memory.json`）。
> - 對話 LLM = LAN 內自架，**非雲端**。
> - Embedding = 本機 Python process 內推論，**非雲端**。
> - 三者互相獨立：記憶系統不知道 LLM 在哪、LLM 不知道有記憶系統。

---

## 3. 安裝與測試

```bash
# 1) 核心（capture/store/retrieve/bm25/tests）只需 stdlib + pytest
pip install -r requirements.txt

# 2) 跑測試（含核心 13 題 + 進階 15 題）
pytest -q
# → 28 passed
# （pytest.ini 已設 `pythonpath = .`，不必另外 export PYTHONPATH）
```

CI 要綠燈，只需 `pytest -q` 全部通過、必繳檔案齊全（見下方）。

---

## 4. 跑 Benchmark

```bash
# 小語料 30 筆 / 21 題（與單元測試同等級）
PYTHONPATH=. python benchmark/run_benchmark.py --k 5 --per-query

# 大語料 100 筆 / 40 題（自行探索）
PYTHONPATH=. python benchmark/run_benchmark.py \
    --corpus corpus_large.jsonl --queries queries_large.jsonl --k 5 --per-query

# 開啟 hybrid（BM25 + embedding，用 RRF 融合）
PYTHONPATH=. PI_RETRIEVAL=hybrid python benchmark/run_benchmark.py --k 5 --per-query
PYTHONPATH=. PI_RETRIEVAL=hybrid python benchmark/run_benchmark.py \
    --corpus corpus_large.jsonl --queries queries_large.jsonl --k 5 --per-query
```

實測（k=5）：

| 設定 | Recall@5 | MRR | nDCG@5 |
|---|---|---|---|
| 小語料｜pure BM25 | **0.810** | 0.810 | 0.802 |
| 小語料｜hybrid    | **0.857 ↑** | 0.833 ↑ | 0.840 ↑ |
| 大語料｜pure BM25 | **0.838** | 0.826 | 0.795 |
| 大語料｜hybrid    | **0.863 ↑** | **0.943 ↑↑** | 0.869 ↑ |

詳細逐題分析、為什麼 hybrid 修好那幾題、為什麼還有沒修好的，請見 [REPORT.md](REPORT.md)。

---

## 5. 接到 Pi 跑 Demo

```bash
# 1) 把示範設定複製成 Pi 的模型清單，改成你的實際 model id
cp models.json.example ~/.pi/agent/models.json
# 內含 ollama-remote provider 指向 LAN 內 Ollama；改 baseUrl / model 為你的設定

# 2) 在 repo 根目錄啟動 Pi、掛 extension
cd /path/to/AIASE2026-HW4
PYTHONPATH=. pi -e ./pi-bridge/extension.ts
```

bridge 會以 `import.meta.url` 推導 repo root，並在呼叫 Python 時設 `PYTHONPATH=REPO_ROOT`，跨平台都會找得到 `memory/`。

### ⚠️ 若把 extension 複製到 `~/.pi/agent/extensions/` 由 Pi 自動載入

上面的「在 repo 根目錄用 `pi -e ./pi-bridge/extension.ts`」做法，bridge 的 `new URL("..", import.meta.url)` 會正確指到 repo 根（因為 extension 還在 `<repo>/pi-bridge/` 底下）。

但如果你把 `extension.ts` **複製**到 `~/.pi/agent/extensions/` 讓 Pi 自動載入，`import.meta.url` 就會變成 `~/.pi/agent/extensions/extension.ts`，它推出的 `REPO_ROOT` 會是 `~/.pi/agent/`，**不是作業 repo 根目錄，因此 Python 找不到 `memory/` 套件**。此時請用下列任一方式把 Python 指回 repo（請把 `/abs/path/to/AIASE2026-HW4` 換成你機器上的絕對路徑）：

**做法 A（推薦）— 不要複製，用符號連結 + repo 根啟動。** 維持單一 source of truth，bridge 的相對推導照樣成立：

```bash
ln -s /abs/path/to/AIASE2026-HW4/pi-bridge/extension.ts ~/.pi/agent/extensions/pi-memory.ts
cd /abs/path/to/AIASE2026-HW4
PYTHONPATH=/abs/path/to/AIASE2026-HW4 pi          # 讓 Python 用絕對路徑找到 memory/
```

**做法 B — 真的要複製，就用環境變數把 `PYTHONPATH` 釘成絕對路徑。** 在啟動 Pi 的 shell（或 `~/.bashrc` / `~/.zshrc`）設定：

```bash
export PYTHONPATH=/abs/path/to/AIASE2026-HW4    # 絕對路徑，cwd 在哪都找得到 memory/
export PI_MEMORY_PATH=/abs/path/to/.pi-memory.json   # 記憶檔也建議用絕對路徑，避免依賴 cwd
pi                                               # Pi 從 ~/.pi/agent/extensions/ 自動載入
```

> 重點：bridge 呼叫 `python -m memory.cli` 時會把目前環境的 `PYTHONPATH` 一併傳下去，所以**只要在啟動 Pi 的環境設好絕對路徑的 `PYTHONPATH`，不論 extension 放哪、cwd 在哪，bridge 都能正確呼叫 Python 記憶系統**。跨平台（Windows 用 `set PYTHONPATH=...` / PowerShell 用 `$env:PYTHONPATH=...`）行為亦同，請依你的 shell 自行調整。

### 進階功能開關（demo 時用環境變數打開）

```bash
PI_PRIVACY=1                            # 進入存儲前遮蔽 sk-/ghp-/password=
PI_RETRIEVAL=hybrid                     # retrieve() 改走 BM25 + embedding (RRF)
PI_DECAY=1 PI_DECAY_HALFLIFE_DAYS=14    # 排序乘上 last_used_at 指數衰減
PI_EMBED_BACKEND=st                     # st (預設) | ollama
PI_EMBED_MODEL=...                      # 換 embedding 模型
PI_OLLAMA_URL=http://192.168.63.184:11434
PI_MEMORY_PATH=~/.pi-memory.json
```

Demo 場景與錄影連結見 [`demo/README.md`](demo/README.md)。

---

## 6. 我做了哪些任務二

| 進階功能 | 模組 | 開關 | 設計重點 |
|---|---|---|---|
| **A. Hybrid retrieval** | `memory/hybrid.py` | `PI_RETRIEVAL=hybrid` | BM25 + sentence-transformers embedding，用 **RRF (k=60)** 融合排名。不需要校正分數尺度，對單通道離群分數魯棒 |
| **B. 隱私過濾** | `memory/privacy.py` | `PI_PRIVACY=1` | regex 遮蔽 OpenAI `sk-…`、Anthropic `sk-ant-…`、GitHub `ghp_…`、AWS `AKIA…`、`Bearer …`、`password=…`。保留前綴方便人工辨識，避免「整段消失看不出曾遮過」 |
| **C. 遺忘 Decay** | `memory/decay.py` | `PI_DECAY=1` | `weight = exp(-ln2·age/half_life)`（Ebbinghaus），預設 30 天半衰期。命中後 touch `last_used_at`，但**不會刪除**任何記憶 — 持久性是契約 |
| **D. `/recall` `/forget` CLI** | `memory/cli.py` + `pi-bridge/extension.ts` | 永遠可用 | `recall` 可選關鍵字過濾；`forget` 自動辨識 64 hex 為 id、否則當 summary。讓使用者可手動審視、修剪記憶 |

完整反思（為何選 RRF 而非加權平均、為何 decay 預設關閉、隱私 trade-off 等）請見 REPORT。

---

## 7. 必繳檔案清單對照

```
HW4/
├── memory/                    bm25.py · store.py · core.py · cli.py · hybrid.py · privacy.py · decay.py · embed.py
├── tests/                     test_memory.py（13 題公開） + test_advanced.py（15 題進階）
├── benchmark/                 run_benchmark.py · corpus(.jsonl + _large.jsonl) · queries(...)
├── pi-bridge/                 extension.ts（remember 工具 + /recall + /forget 命令）
├── fixtures/                  observations.json
├── demo/                      README.md（D2/D3/D4 三個場景說明 + 連結）
├── requirements.txt
├── README.md                  本檔
├── REPORT.md                  7 大反思 + benchmark 詳細分析
├── models.json.example        ollama-remote provider 範例
└── .github/workflows/ci.yml   必要檔案存在性檢查 + pytest -q
```

---

## 8. 常用一鍵指令

```bash
# 看記憶（CLI 直接呼）
PYTHONPATH=. python -m memory.cli list
PYTHONPATH=. python -m memory.cli list --query pnpm
PYTHONPATH=. python -m memory.cli forget --summary "use pnpm not npm"

# 寫一筆記憶
PYTHONPATH=. python -m memory.cli capture --summary "this project uses pnpm" --tags build

# 開 hybrid + decay 跑一次 benchmark
PYTHONPATH=. PI_RETRIEVAL=hybrid PI_DECAY=1 python benchmark/run_benchmark.py --k 5
```
