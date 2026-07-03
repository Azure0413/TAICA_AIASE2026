# Demo — 跨 session 記憶 + 任務二進階功能

> **影片連結（必看，≈ 90 秒）**：
> **🎬 https://youtu.be/F7HbVZuHJ7Q**
>
> 影片內容是一鍵腳本 `bash demo/record_all.sh` 的完整輸出，
> 涵蓋 pytest 全綠、純 BM25 / Hybrid benchmark、跨 session 記憶、隱私過濾、`/recall` `/forget`。
> 全程跑在 **LAN 內自架 Ollama + 本機 Python 記憶系統，零雲端 API 呼叫**。

---

## 影片內容對照（同步附 6 張關鍵截圖）

| # | 影片段落 | 截圖 |
|---|---|---|
| ① | **28 個 pytest 全綠 + 純 BM25 benchmark**（小語料 0.810 / 大語料 0.838 — 精準命中助教參考值） | [01-tests-and-bm25-benchmark.png](01-tests-and-bm25-benchmark.png) |
| ② | **Hybrid retrieval benchmark**（小語料 0.810 → 0.857；大語料 MRR 0.826 → 0.943） — 任務二 A 的客觀證據 | [02-hybrid-benchmark.png](02-hybrid-benchmark.png) |
| ③ | **跨 session 記憶**：Session A 寫入三件事 → 硬碟有 JSON 檔 → Session B（另一個 process）retrieve + inject 拿回 | [03-cross-session-memory.png](03-cross-session-memory.png) |
| ④ | **任務二 B — 隱私過濾 `PI_PRIVACY=1`**：使用者貼進 `sk-…` / `ghp_…` / `password=…`，硬碟上自動遮成 `[REDACTED]` | [04-privacy-filter.png](04-privacy-filter.png) |
| ⑤ | **任務二 D — `/recall` + `/forget` CLI**：使用者可列出記憶、依 summary 刪除，刪後 list 確認 | [05-recall-and-forget-cli.png](05-recall-and-forget-cli.png) |
| ⑥ | **Demo 結束總結**（28 tests / Hybrid 全升 / 任務二 4 項 / 跨 session 持久化） | [06-demo-summary.png](06-demo-summary.png) |

---

## 一鍵重現影片內容

任何人 clone 這個 repo 後，跑一行指令就能完整重現影片裡看到的所有東西：

```bash
cd AIASE2026-HW4
PYTHONPATH=. bash demo/record_all.sh
```

腳本會自動依序展示 ①–⑥ 全部，總長 ≈ 90 秒。**不需要 Pi runtime**，純 Python CLI 即可示範「跨 session 記憶生效」（影片裡的 Session A → 硬碟 JSON → Session B 是兩個獨立 Python process）。

---

## 接到 Pi 跑（如果你要在真實 agent 環境驗證）

```bash
# 0) 清空當前記憶（避免上次的雜訊影響觀察）
rm -f ~/.pi-memory.json

# 1) 把示範設定複製成 Pi 的模型清單，改成你的 Ollama IP
cp models.json.example ~/.pi/agent/models.json
# 修 baseUrl 為你的 Ollama IP；本作業用 http://192.168.63.184:11434/v1（LAN 內自架）

# 2) 在 repo 根目錄啟 Pi、掛 extension
cd /path/to/AIASE2026-HW4
PYTHONPATH=. pi -e ./pi-bridge/extension.ts
```

進入 Pi 後：

| 場景 | Session A 輸入 | Session B 輸入 | 預期行為 |
|---|---|---|---|
| **D2 跨語言** | `記住：我們的資料庫用 PostgreSQL，向量索引用 pgvector` | `what database do we use, and how do we store embeddings?`（需開 `PI_RETRIEVAL=hybrid`） | hybrid 命中那筆中文記憶 → agent 直接回 PostgreSQL + pgvector |
| **D3 多項偏好** | 連說 5 件事（pnpm、commit 用中文、ruff/black、Fly.io、PR + 核可） | `我要 commit 改動然後 deploy，整個流程要做哪些事？` | agent 依注入內容輸出完整流程，不需反問 |
| **D4 隱私過濾** | `API_KEY=sk-PROJ0000abcdEFGHabcdEFGH1234XYZ`（需開 `PI_PRIVACY=1`） | `/recall API_KEY` | 列出來的內容是 `API_KEY=[REDACTED]`，硬碟 JSON 也是 |

每段 Session A 結束後 `/quit`，再啟一次 Pi 跑 Session B —— 跨 process 證明「跨 session 記憶生效」。

---

## 個別場景的 CLI 重現腳本（不需要 Pi）

如果你想跑單一場景驗證，每個都有獨立腳本：

```bash
bash demo/run_demo_d2_hybrid.sh    # 跨語言（中文存、英文撈）
bash demo/run_demo_d3.sh           # 多項偏好注入
bash demo/run_demo_d4_privacy.sh   # 隱私過濾
```
