# HW4 自動評分回饋 — hw4-pi-memory-Azure0413

> 本回饋由自動評分系統產生。**核心記憶迴路正確性**由 `pytest`（公開＋隱藏單元測試）客觀計分，
> 可重現、不可灌水；**Benchmark / 進階功能 / 反思報告**等主觀項，由兩個大型語言模型
> （Claude Opus 4.8 與 ChatGPT gpt-5.5）獨立評分後取平均。本回饋僅含你個人的評量，未與其他同學比較。

## 分數總覽

| 校正後最終分數 | Opus 4.8 評分 | ChatGPT gpt-5.5 評分 |
|:---:|:---:|:---:|
| **90.4 / 100** | 96.7 | 98.25 |

> 「校正後最終分數」＝兩模型平均（加權原始分 raw = 97.5）經全班保序校準至 60–95。
> Opus / ChatGPT 兩欄為各模型**獨立**的綜合評分（採與最終分相同的加權計法），供你對照。

## 各面向得分

| 面向 | 權重 | 得分 (0–100) | 來源 |
|---|---|---|---|
| A. 核心記憶迴路正確性 | 40% | **100.0** | pytest（客觀） |
| B. Benchmark 表現與分析 | 20% | **96.0** | 客觀 100 ＋ LLM 92 |
| C. 進階功能（任務二） | 20% | **97.0** | 客觀 100 ＋ LLM 94 |
| D. 反思報告與可重現性 | 20% | **94.4** | 客觀 100 ＋ LLM 92 |

## A. 核心正確性（客觀單元測試）

| 測試群組 | 通過 | 權重 |
|---|---|---|
| BM25 排序正確性 | 6/6 | 30 |
| BM25 數值正確性 | 2/2 | 20 |
| 邊界 / 同分穩定 | 7/7 | 15 |
| tokenize | 4/4 | 10 |
| store 持久化 / 去重 | 7/7 | 15 |
| capture / retrieve / inject | 4/4 | 10 |

核心得分 **A = 100.0 / 100**（依群組加權通過率）。

## B. Benchmark（系統實測，非你 REPORT 的宣稱值）

- 純 BM25　小語料：Recall@5=0.810 / MRR=0.810 / nDCG@5=0.802　（官方參考 0.810 / 0.810 / 0.802）
- 純 BM25　大語料：Recall@5=0.838 / MRR=0.826 / nDCG@5=0.795　（官方參考 0.838 / 0.826 / 0.795）
- Hybrid（大語料）：Recall@5=0.863 / MRR=0.943 / nDCG@5=0.869；相對純 BM25 的 Recall delta = +0.025

## C. 進階功能（任務二）

- 偵測到的模組：embed、decay、hybrid、privacy

## 評語（兩個模型獨立評分，僅供回饋）

### Claude Opus 4.8
B Benchmark分析 92：純 BM25 兩組分數與實測完全一致（小0.810/0.810/0.802、大0.838/0.826/0.795），並具體點出三類接不到的題目：詞彙不匹配（package manager vs pnpm）、同義詞（picture vs image）、跨語言（中文查詢對英文記憶），且解釋了 distractor 稀釋（payment provider 的 IDF 被稀釋）。§2.4 還誠實列出 hybrid 仍接不到的題目並分析原因，分析具體且與檢索原理相符。
C 進階設計 90：任務二做滿四項（hybrid/decay/privacy/CLI）且相互正交。Hybrid 選 RRF 並清楚論證為何不用加權平均（尺度不一致、校正會 overfit），pool=50 與 bm25_only fallback 設計合理，明確保留純 BM25 預設路徑符合硬性要求。harness 實測 hybrid 大語料 MRR 0.943、Recall delta +0.025 支持其改進宣稱。trade-off（rerank/query expansion 不划算）也有
D 反思/可重現 90：七問完整且深入：gaming 以固定資料+純函式契約+隱藏測試論證不可作弊；確定/機率分界細到 embedding『準確定』與浮點誤差；token 預算 2000 引 Lost-in-the-Middle 並說明取捨；與 /compact 區分 session 內外；vs PROGRESS.md 從召回/精度/可審計多軸比較並給明確邊界。環境記錄詳實（Python 3.13.5、LAN Ollama、本機 CPU embedding）。README 安裝測試步驟清楚，並貼心提

### ChatGPT gpt-5.5
B Benchmark分析 92：純 BM25 數字與實測完全一致，並能具體說明詞彙不匹配、跨語言與 distractor 稀釋；但未完整逐題列出所有失敗查詢。
C 進階設計 98：Hybrid 以 RRF 融合 BM25 與 embedding，trade-off、fallback 與環境開關清楚，保留純 BM25；實測 MRR/nDCG 也有明顯提升。
D 反思/可重現 95：七問回答完整且具工程反思，README 含測試、benchmark 與環境記錄；完整 demo 仍依賴 LAN Ollama 或模型下載設定需使用者調整。

## 備註（中性事實，僅供參考）

> 以下為系統偵測到的客觀事實，非指控、亦非扣分依據。

- 無

---
*評分方式：核心 40% 由公開／隱藏 `pytest` 客觀計分；其餘 60% 由雙模型平均。如對分數有疑問，請依課程公告之申訴管道聯繫助教。*
