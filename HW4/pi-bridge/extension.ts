// Pi bridge（已提供，學生「不需」修改）。
// 讓 Pi 透過 CLI 呼叫本作業的 Python 記憶系統：
//   - before_agent_start：呼叫 `python -m memory.cli inject` 取得注入文字，回傳 { message }
//   - remember 工具       ：呼叫 `python -m memory.cli capture` 寫入記憶
//
// 重要：本檔依 earendil-works/pi 目前的 extension API 撰寫。
// 官方文件：https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md
//
// 執行方式（務必在作業 repo 根目錄，並設定 PYTHONPATH，讓 python 找得到 memory/ 套件）：
//   cd AIASE2026-HW4
//   PYTHONPATH=. pi -e ./pi-bridge/extension.ts
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { spawnSync } from "node:child_process";

const PY = process.env.PYTHON ?? "python3";
// 固定以 extension 所在 repo 的根目錄為 cwd，避免從其他位置啟動時找不到 memory/ 套件。
// import.meta.url 形如 file:///.../AIASE2026-HW4/pi-bridge/extension.ts
const REPO_ROOT = new URL("..", import.meta.url).pathname;

function callMemory(args: string[]): string {
  const r = spawnSync(PY, ["-m", "memory.cli", ...args], {
    encoding: "utf8",
    cwd: REPO_ROOT,
    env: { ...process.env, PYTHONPATH: REPO_ROOT },
  });
  if (r.status !== 0) {
    return ""; // 失敗時不注入，避免中斷 agent
  }
  return (r.stdout ?? "").trim();
}

export default function (pi: ExtensionAPI) {
  // ── 注入：agent 開工前，用使用者輸入檢索相關記憶並注入 ──
  pi.on("before_agent_start", async (event, _ctx) => {
    const query: string = event.prompt ?? "";
    if (!query) return;
    const memo = callMemory(["inject", "--query", query, "--budget", "2000"]);
    if (!memo) return;
    return {
      message: {
        customType: "pi-memory",
        content: memo,
        display: true,
      },
    };
  });

  // ── 捕捉（方式 A）：註冊 remember 工具 ──
  pi.registerTool({
    name: "remember",
    label: "Remember",
    description:
      "When the user states a durable project convention, preference, or important " +
      "fact that should persist across sessions, call this to remember it.",
    promptGuidelines: [
      "Use remember when the user states a durable project convention, preference, or fact worth keeping across sessions.",
    ],
    parameters: Type.Object({
      summary: Type.String({ description: "The fact to remember, one sentence." }),
      tags: Type.Optional(Type.Array(Type.String())),
    }),
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const tags = (params.tags ?? []).join(",");
      const out = callMemory(["capture", "--summary", params.summary, "--tags", tags]);
      return {
        content: [{ type: "text", text: out || `Remembered: ${params.summary}` }],
        details: {},
      };
    },
  });

  // ── /recall：列出目前所有記憶（可選關鍵字過濾） ──
  // 由使用者手動觸發，便於 demo 與除錯。
  (pi as any).registerCommand?.({
    name: "recall",
    description: "List stored memories (optionally filter by keyword)",
    async execute(args: string[] | undefined) {
      const query = (args ?? []).join(" ");
      const out = callMemory(
        query ? ["list", "--query", query] : ["list"]
      );
      return { message: out || "(no memories)" };
    },
  });

  // ── /forget：刪除一筆記憶（以 summary 文字或 id） ──
  (pi as any).registerCommand?.({
    name: "forget",
    description: "Forget a memory by summary text or id",
    async execute(args: string[] | undefined) {
      const text = (args ?? []).join(" ").trim();
      if (!text) return { message: "Usage: /forget <summary text or id>" };
      // 64 字小寫 hex 視為 id；其餘視為 summary 文字
      const flag = /^[0-9a-f]{64}$/.test(text) ? "--id" : "--summary";
      const out = callMemory(["forget", flag, text]);
      return { message: out || "(no-op)" };
    },
  });
}
