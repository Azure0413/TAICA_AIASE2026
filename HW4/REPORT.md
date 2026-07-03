# HW4 反思報告 — Pi Memory

> Memory Engineering for Agents — Capture / Store / Retrieve / Inject
> 對應作業要求的七個反思題；分數以實測為主，環境記錄附在最後。
>
> **🎬 Demo 影片**：https://youtu.be/F7HbVZuHJ7Q
> **📂 截圖與場景說明**：見 [`demo/README.md`](demo/README.md)

---

## 1. 我如何判斷「記憶有效」？這個指標為何不可被作弊？

**「有效」= 同一份固定語料、固定查詢、固定標準答案下，
`retrieve()` 把標準答案放進前 K 名的能力。**
用三個資訊檢索界長期共識的指標一起看：

| 指標 | 它在問什麼 | 補了什麼缺口 |
|---|---|---|
| **Recall@k** | 標準答案落在前 K 裡的比例 | 「有沒有撈到」最直觀 |
| **MRR** (Mean Reciprocal Rank) | 第一個命中答案的倒數排名平均 | 排名在第 1 vs 第 5 顯然差別很大，Recall 看不出 |
| **nDCG@k** | 多個相關答案時，依排名打折扣後的加權命中量 | 處理「一題有多個相關答案」的情況（e.g. `"which database…?"` 對應 `o05` + `o15`） |

**不可作弊**的條件來自設計，而非紀律：

1. **語料和標準答案是固定的 JSONL**（`benchmark/corpus.jsonl` / `queries.jsonl`），任何人在乾淨環境 `git pull` 都會得到相同數字。
2. **retrieve 預設是純函式 BM25**（`memory/bm25.py`，無 RNG、無外部呼叫、不讀環境變數）—— 同樣輸入永遠同樣輸出。
3. **作弊 = 改 bm25_search() 的回傳順序**會被**隱藏單元測試（與公開測試同格式、不同資料）**抓到。隱藏測試會跑像「`pnpm test` 三筆樣本 D1/D3 進前 2、D2 為 0 分」這種數學上唯一解的 case，無法 hack。
4. **作弊 = 在 retrieve 加入「query 中包含 pnpm 就回傳 d1」這種規則**會在隱藏測試的不同資料上立刻露餡（IDF 比例會錯）。
5. 我把進階 hybrid 放在獨立函式 `hybrid_search()` 並由 `PI_RETRIEVAL=hybrid` 啟用 —— 預設路徑不被污染，**評分時看到的是純 BM25**。

換句話說：「指標」+「固定資料」+「函式純度契約」三者構成 falsifiability。
不是「相信我」，是「自己跑一次驗」。

---

## 2. Benchmark 分數與錯誤分析

### 2.1 純 BM25（**自動評分對應的預設路徑**）

| 資料集 | Recall@5 | MRR | nDCG@5 | 參考目標（題目給定） |
|---|---|---|---|---|
| 小語料（`corpus.jsonl`，30 筆 / 21 題） | **0.810** | 0.810 | 0.802 | Recall@5 ≈ 0.810 |
| 大語料（`corpus_large.jsonl`，100 筆 / 40 題） | **0.838** | 0.826 | 0.795 | Recall@5 ≈ 0.838 |

兩組分數**精確命中題目給定的助教參考實測**。

### 2.2 任務二 hybrid retrieval（BM25 + multilingual MiniLM + RRF）

| 資料集 | Recall@5 | MRR | nDCG@5 |
|---|---|---|---|
| 小語料｜hybrid | **0.857 ↑ +0.047** | **0.833 ↑ +0.023** | **0.840 ↑ +0.038** |
| 大語料｜hybrid | **0.863 ↑ +0.025** | **0.943 ↑↑ +0.117** | **0.869 ↑ +0.074** |

**重點觀察**：MRR 的大幅躍升（大語料 +0.117）來自「即使 Recall 沒升、第一筆命中的 rank 從 3/4 變 1/2」——
這正是 RRF 的設計目的，融合兩個正交訊號讓正確答案的排名更穩定。

### 2.3 純 BM25 接不到、hybrid 修好的題目

| 題目 | 純 BM25 → | hybrid → | 為什麼 |
|---|---|---|---|
| 「what package manager should I use?」 / 大語料 | ✗（全是 distractor） | ✓ L001 | **詞彙不匹配**：查詢說 "package manager"，記憶寫 "pnpm / npm" — 字面零交集，BM25 整題零分；MiniLM 學過「pnpm 是 package manager」的語義關聯 |
| 「how big can an uploaded picture be?」 / 大語料 | ✗ | ✓ L048+L089 | "picture" vs "image"（同義詞），BM25 完全接不到；embedding 認得是近義詞 |
| 「怎麼確認我的程式碼風格符合規範？」 / 小語料 | ✗ | ✓ o07 | **跨語言**：中文「程式碼風格符合規範」要對到英文「Code style is enforced by ruff and black」。`tokenize()` 把中文逐字切，BM25 沒共同 token；多語 MiniLM 將中英對應概念投到同一語意空間 |

### 2.4 hybrid 仍接不到的題目（值得討論）

| 題目 | 標準答案 | 觀察 |
|---|---|---|
| 「when is the team sync meeting each week?」 / 小語料 | o24「週會固定在每週二早上十點」 | 跨語言 + 一詞多義（meeting → 週會 → 會議）。MiniLM 距離不夠近、被中文化 distractor 擠下 |
| 「我要怎麼把新功能慢慢開放給部分使用者？」 / 小語料 | o27「feature flags via LaunchDarkly for gradual rollouts」 | 中→英抽象概念（feature flag），語料中沒任何字面 hint，連 embedding 都對應到「逐步」的近詞而不是 LaunchDarkly |
| 「what payment provider do we use?」 / 大語料 | L077「Payments are processed by Stripe」 | "payment provider" → 字面 "Payments" 對得到，但 "provider" 在 100 筆中常見、IDF 被稀釋；hybrid pool=50 的 embedding 通道把 Stripe 排在 6~10 名，沒進前 5 |

**啟示**：embedding 不是萬靈丹；剩下這幾題還需要 **rerank（cross-encoder）** 或 **query expansion（讓 LLM 重寫查詢）**才能修好。
這是 production-grade RAG 的下一步，但對本作業 token 預算與 cost-budget 來說不划算，因此沒做。

---

## 3. 系統哪些部分是確定性的、哪些是機率性的？為什麼這樣切？

| 區塊 | 確定／機率 | 為什麼這樣切 |
|---|---|---|
| **`bm25_search` 計分排序** | 確定 | 公式可重現，可被單元測試二進位比對 → 適合自動評分 |
| **`JsonStore.add` 去重 / `_persist`** | 確定 | I/O 雖有外部副作用，但寫的內容由輸入決定 → 仍可寫單元測試覆蓋（test_dedup / test_persistence） |
| **`make_observation` 的 id** | 確定 | SHA-256(summary)，相同 summary 永遠相同 id |
| **Hybrid 的 BM25 通道** | 確定 | 同 BM25 |
| **Hybrid 的 embedding 通道** | **準確定** | 固定模型 + 固定權重 → 確定；但浮點誤差、跨硬體 GPU/CPU 微差不可控（誤差 ~1e-7） |
| **RRF 融合排序** | 確定 | 只看排名 |
| **`remember` 工具該不該叫** | **機率** | 由 LLM 決定，prompt + 模型強度直接影響 — 一個 7B 模型可能太貪心或太保守 |
| **使用者輸入** | **不可控** | 不在系統範圍內 |

**設計哲學**：「機率性的部分（LLM 決定要不要 capture）」用「確定性的契約（store/retrieve 兩個純函式）」包起來。
模型再不穩，至少 retrieve 的行為 100% 可預測 → 出錯時可二分定位是「沒記」還是「沒撈到」。
這就是題目所說的 **Verifiability Mindset**。

---

## 4. 注入的 token 預算我設多少？太多 / 太少各有什麼代價？

**預設 2000 tokens**（`build_injection` 的 default `token_budget=2000`）。理由：

- 7B/8B 級的本地模型常見 context 8K~32K；扣掉 system prompt、工具定義、對話歷史，留給「外部注入」實際只剩 4K~8K。
- 2000 約佔 25%~50%，能塞下 20–30 筆精短記憶。在 21 題的 benchmark 上 retrieve(k=8) 永遠進得了預算上限。

| 策略 | 太大（如 4000+） | 太小（如 500） |
|---|---|---|
| **直接成本** | 每次 inference 都多 4000 tokens × token price → 跑本地模型也是延遲懲罰（QPS 下降） | 省 token |
| **模型行為** | **「Lost-in-the-Middle」**：注入越長，模型越容易忽略中段資訊（Liu 2023） | 模型可能只看到不相關的記憶（top-5 不夠涵蓋） |
| **可解釋性** | 注入內容多到「為什麼模型給這個答案」難追溯 | 容易說「就是這 3 筆說 pnpm」 |
| **任務干擾** | 跨主題記憶混入會帶歪當前 task | 該記得的沒帶到，agent 反問或猜錯 |

**我的折衷**：固定 2000、依 BM25 排序高分到低分塞、塞到下一筆會爆預算就停。
**沒有**做「按 retrieved score 動態收縮 budget」，因為這會破壞 budget 的契約，使行為更難解釋。

---

## 5. 我的記憶外掛和 `/compact` 是互補還是競爭？

**互補。它們解的是不同層的問題。**

| 軸 | `/compact` | 我的記憶外掛 |
|---|---|---|
| 範圍 | 同一個 session 內 | 跨 session |
| 持久化 | 否（session 結束就沒了） | 是（寫硬碟 JSON） |
| 觸發 | 使用者手動 / context 將滿 | `before_agent_start` 自動 + `remember` 工具 |
| 內容 | 把長對話濃縮成摘要繼續用 | 抽出「durable convention / preference / fact」存起來 |
| 失敗後果 | 對話遺失上下文（這次 session 變笨） | 下次 session 還是會重新問你「我們用 pnpm 嗎」 |

實際使用：今天我跟 agent 改 100 個檔案、context 滿 → `/compact` 壓掉細節繼續工作；
中間我說「測試用 pnpm test」→ agent 呼叫 `remember` → JSON 寫盤 →
明天開新 session 問「跑測試」→ 我的外掛在 `before_agent_start` 注入「pnpm test」回 context。

兩者**沒有競爭**：`/compact` 解的是「即時上下文視窗有限」，
我的外掛解的是「session 之間沒有狀態」。
業界做 production agent 時通常**兩個都要**（Devin、Cursor Background、Claude Projects 皆是如此）。

---

## 6. 我的自動記憶系統 vs 人工手寫 `PROGRESS.md`，各有何優缺點？何時寧可手寫？

| 維度 | 自動記憶（我的系統） | 手寫 `PROGRESS.md` |
|---|---|---|
| **召回率** | 高 — 24 / 7 在記，使用者忘了寫的也會記下 | 低 — 你忘了寫就沒了 |
| **精度** | 中 — LLM 可能誤判什麼值得記、寫進雜訊 | 高 — 寫進去的都是你親手過濾過的 |
| **可審計** | 中 — 要跑 `/recall` 才能看；JSON 結構統一 | 高 — Markdown，diff 友善、PR 可審 |
| **與專案歷史的耦合** | 弱 — 是「個人 / 機器」的記憶 | 強 — 是團隊知識資產，新人 onboarding 就讀它 |
| **失敗模式** | 沉默退化 — 哪天 retrieve 接錯，agent 也只是少 inject 不會爆 | 顯性過時 — Markdown 不更新會被同事抓出來 |
| **時效** | 自動 touch `last_used_at`，stale 的自然下沉（decay 開啟時） | 需人工 review |

**寧可手寫的時機**：
1. **架構決策**（ADR）— 需要團隊集體 review、需要長期可追溯的 commit history。
2. **新人 onboarding**— 文件必須線性可讀，不是「靠 retrieve 撞」。
3. **法遵 / 合規 / 安全條款**— 寫漏一條會出事，**召回率必須是 1**，不能仰賴機率排序。
4. **跨團隊共享的知識**— `PROGRESS.md` 在 GitHub 上，記憶系統在我硬碟上。

**寧可自動的時機**：
1. **個人偏好**（commit 用中文、用 pnpm 不用 npm）— 寫進 `PROGRESS.md` 太重，會被同事覺得「這是你個人事」。
2. **跨 session 的脈絡延續**— agent 不可能自動讀 `PROGRESS.md` 然後找出當前任務相關段落，但記憶系統可以。
3. **長尾 fact**（「外部 API X 在 Y 情況下會吐 Z」）— 多到不可能維護 markdown。

我的看法：**兩者一起用，邊界清楚**。把 `PROGRESS.md` 當「人類審稿過的官方資產」，把記憶系統當「agent 私有的工作便條」。
我的外掛也許未來可以加 `--from PROGRESS.md` 把 markdown 同步進記憶，但目前不做（避免兩個 source of truth 衝突）。

---

## 7. 環境記錄與任務二設計

### 環境

| 項目 | 值 |
|---|---|
| Python | **3.13.5**（assignment 要求 `>= 3.10`） |
| 對話 LLM | `qwen2.5:7b`（或 `gpt-oss:20b`） |
| 後端 | **Ollama，自架於 LAN 另一台主機**（`http://192.168.63.184:11434`，OpenAI-compatible `/v1`） |
| Context size | 32K（Qwen 2.5 預設） |
| 寄宿硬體 | LAN 內部 GPU server，VRAM 充足以執行 7B / 20B 量化模型 |
| Embedding（任務二） | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，本機 Python CPU 推論；模型權重首次從 HuggingFace 下載並快取於 `~/.cache/huggingface/`，後續完全離線 |

> **無雲端 API 呼叫**：對話 LLM 跑在 LAN 內自架 Ollama；embedding 跑在本機 Python process；記憶 JSON 寫到本機硬碟（`~/.pi-memory.json`）。三者皆不涉及任何雲端付費服務。

### 任務二（4 項都做了，相互正交）

#### A. Hybrid retrieval（`memory/hybrid.py`）— 啟用：`PI_RETRIEVAL=hybrid`

**設計選擇**：
- **RRF (Reciprocal Rank Fusion, Cormack 2009)** 而非加權平均。
  原因：BM25 分數無上界且資料相依（同樣是「第一名」在不同 corpus 上絕對值差數量級），cosine ∈ [-1,1]。
  做加權平均需要校正，校正係數會 overfit benchmark。RRF 只看排名 → 不需校正、可解釋、業界（Elasticsearch、Vespa）標配。
- **pool = 50**：兩個檢索器各取前 50 名再融合，避免「embedding 命中第 51 但 BM25 沒進前 50」這種互補性流失。
- **`bm25_only=True` fallback**：embedding 後端壞了或沒裝，自動退回純 BM25。`bm25_search` 路徑完全不被 hybrid 污染。

**證據**：見 §2.3 / §2.4。

#### B. 隱私過濾（`memory/privacy.py`）— 啟用：`PI_PRIVACY=1`

**設計選擇**：
- 純 regex 遮蔽（OpenAI `sk-…`、Anthropic `sk-ant-…`、GitHub `ghp_…`、AWS `AKIA…`、`Bearer …`、`password=…`）。
- 保留前綴（如 `sk-abcd`）方便人工識別「這裡曾遮過金鑰」，而不是整段消失。
- **遮蔽在 `capture()` 入口**，落地之前就改 `summary` 與 `id`（重新算 SHA-256）— 一旦寫進 JSON 就不可逆。
- **不啟用「高熵亂數一律遮」**（commented out），避免誤殺 hash、UUID、commit SHA 這類正當欄位。

#### C. 遺忘 Decay（`memory/decay.py`）— 啟用：`PI_DECAY=1 PI_DECAY_HALFLIFE_DAYS=30`

**設計選擇**：
- 指數衰減 `weight = exp(-ln2 · age_days / half_life_days)`，半衰期預設 30 天（對應 Ebbinghaus 一個月）。
- 命中時 touch `last_used_at`（不影響當次排序，影響的是**下次**），實現「越常被用、越不會被遺忘」。
- 設 `floor=0.2` 下限：再久沒用的也不會分數歸零，避免「永遠撈不到 → 永遠不會 touch → 永遠沉底」這種惡性循環。
- **不會刪除**任何記憶（持久性是契約）。決定是否丟掉留給使用者用 `/forget`。

#### D. `/recall` `/forget` CLI（`memory/cli.py` + `pi-bridge/extension.ts`）

**設計選擇**：
- `recall` 預設列全部、可加關鍵字 substring 過濾（`/recall pnpm`）。輸出含時間、tags、id 前 10 字 + summary。
- `forget` 自動辨識：64 字小寫 hex → `--id`；其他 → `--summary`，呼叫 SHA-256 算回 id。降低使用者誤刪的門檻。
- bridge 用 `(pi as any).registerCommand?.(...)` 加可選鏈，**舊版 Pi 沒這個 API 也不會 crash**。
