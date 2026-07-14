import path from "node:path";
import fs from "node:fs";
import os from "node:os";
import { fileURLToPath } from "node:url";
import type { Hooks, PluginInput, PluginOptions } from "@opencode-ai/plugin";
import { tool } from "@opencode-ai/plugin";
import { MCPRelay } from "./mcp-relay.js";
import { HealthMonitor } from "./health.js";
import { logger } from "./logger.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const COMPANION_SCRIPT = process.env.BIFROST_COMPANION_PATH || path.resolve(__dirname, "..", "companion", "server.py");

// ── Global skill installer ──────────────────────────────────────────────

const GLOBAL_SKILLS_DIR = path.join(os.homedir(), ".claude", "skills", "fusion");
const GLOBAL_SKILL_PATH = path.join(GLOBAL_SKILLS_DIR, "SKILL.md");

/** Install fusion skill to ~/.claude/skills/fusion/SKILL.md so `/fusion` is available globally. Idempotent. */
function installGlobalFusionSkill(): void {
  try {
    const sourcePath = path.resolve(__dirname, "fusion-skill.md");
    if (!fs.existsSync(sourcePath)) {
      logger.warn(`[bifrost] fusion-skill.md not found at ${sourcePath} — skipping global install`);
      return;
    }

    const content = fs.readFileSync(sourcePath, "utf-8");
    fs.mkdirSync(GLOBAL_SKILLS_DIR, { recursive: true });

    let existing = "";
    try { existing = fs.readFileSync(GLOBAL_SKILL_PATH, "utf-8"); } catch { /* first install */ }

    if (existing !== content) {
      fs.writeFileSync(GLOBAL_SKILL_PATH, content, "utf-8");
      logger.log(`[bifrost] installed global fusion skill → ${GLOBAL_SKILL_PATH}`);
    } else {
      logger.log(`[bifrost] global fusion skill already up to date at ${GLOBAL_SKILL_PATH}`);
    }
  } catch (err) {
    logger.warn(`[bifrost] failed to install global fusion skill (non-fatal):`, err);
  }
}

// ── READ_ONLY_TOOLS — MUST KEEP IN SYNC with companion/classifier/classifier.py ──
const READ_ONLY_TOOLS: ReadonlySet<string> = new Set([
  "Read",
  "Glob",
  "Grep",
  "lsp_diagnostics",
  "lsp_find_references",
  "lsp_goto_definition",
  "lsp_symbols",
  "lsp_status",
  "lsp_prepare_rename",
]);

// ── Types ──────────────────────────────────────────────────────────────

interface ClassifierResult {
  decision: "ALLOW" | "DENY" | "ASK_USER";
  reason: string;
}

/** Shape returned by the companion's fusion_dispatch_tool MCP tool. */
interface FusionResult {
  prompt: string;
  model_responses: Array<{
    model: string;
    response: string;
    cost: number;
    input_tokens: number;
    output_tokens: number;
    wall_time_ms: number;
    timed_out: boolean;
    error: string | null;
  }>;
  fused_answer: string;
  cost: number;
  wall_time_ms: number;
  timed_out_models?: string[];
  label: string;
}

/** Shape returned by the companion's goal_loop MCP tool. */
interface GoalLoopResult {
  goal: string;
  status: string;
  turns_used: number;
  total_cost: number;
  wall_time_ms: number;
  output_summary: string;
  termination_reason: string;
  turns: Array<{
    turn_index: number;
    tool_name: string;
    tool_args: Record<string, unknown>;
    decision: string;
    reason: string;
    estimated_cost: number;
    cumulative_cost: number;
  }>;
}

// ── Helpers ────────────────────────────────────────────────────────────

/** Extract file paths from tool arguments for classifier context. */
function extractFilePaths(
  toolName: string,
  args: Record<string, unknown> | undefined,
): string[] {
  if (!args) return [];

  const paths: string[] = [];

  // Single filePath arg — most tools (Read, Write, Edit, lsp_*)
  if (typeof args.filePath === "string" && args.filePath.trim()) {
    paths.push(args.filePath);
  }

  // Bash command — extract obvious file paths (best-effort, not exhaustive)
  if (toolName === "Bash" && typeof args.command === "string") {
    const cmd = args.command;
    // Match quoted or bare paths: /path/to/file, "./file", "~/file"
    const pathRe = /(["']?)(\/[^\s"']+|\.\/[^\s"']+|~\/[^\s"']+)\1/g;
    let m: RegExpExecArray | null;
    while ((m = pathRe.exec(cmd)) !== null) {
      if (paths.length >= 20) break;
      paths.push(m[2]);
    }
  }

  // Multiple filePaths arg (rare)
  if (
    Array.isArray(args.filePaths) &&
    args.filePaths.every((p): p is string => typeof p === "string")
  ) {
    for (const p of args.filePaths) {
      if (paths.length >= 20) break;
      if (p.trim()) paths.push(p);
    }
  }

  return paths;
}

/** Build a safe session context for the classifier (no tokens/secrets). */
function buildSessionContext(evt: { sessionID: string }): Record<string, unknown> {
  return { session_id: evt.sessionID };
}

// ── Fusion helpers ─────────────────────────────────────────────────────

/** Parse the argument string from `/fusion [args]`. Strips surrounding quotes. */
function parseFusionArgs(raw: string): string {
  if (!raw) return "";
  let s = raw.trim();
  if (
    (s.startsWith('"') && s.endsWith('"')) ||
    (s.startsWith("'") && s.endsWith("'"))
  ) {
    s = s.slice(1, -1).trim();
  }
  return s;
}

function formatUsage(): string {
  return [
    "╔══════════════════════════════════════════════════════════════╗",
    "║  🧪  EXPERIMENTAL — Model Fusion (v1-alpha)                 ║",
    "╚══════════════════════════════════════════════════════════════╝",
    "",
    "**Usage:** `/fusion \"your prompt here\"`",
    "",
    "Sends your prompt to 2-3 AI models in parallel and synthesizes a",
    "fused answer. Default models: `deepseek-v4-pro` + `deepseek-v4-flash`.",
    "Maximum 3 models. Cost ceiling: $0.50 per fusion.",
    "",
    "**Examples:**",
    "```",
    "/fusion \"write a hello world in python\"",
    "/fusion \"explain monads in simple terms\"",
    "```",
  ].join("\n");
}

function formatFusionOutput(result: FusionResult): string {
  const lines: string[] = [];

  lines.push(
    "╔══════════════════════════════════════════════════════════════╗",
    "║  🧪  EXPERIMENTAL — Model Fusion (v1-alpha)                 ║",
    "║  Results are NOT verified. Review before relying on output.  ║",
    "╚══════════════════════════════════════════════════════════════╝",
    "",
    `**Prompt:** ${result.prompt}`,
    `**Wall time:** ${result.wall_time_ms}ms  |  **Total cost:** $${result.cost.toFixed(5)}`,
    "",
  );

  // Per-model responses (collapsible)
  if (result.model_responses.length > 0) {
    lines.push("## Per-Model Responses", "");
    for (const mr of result.model_responses) {
      const status = mr.timed_out
        ? "⏱ TIMED OUT"
        : mr.error
          ? "⚠️ ERROR"
          : "✅";
      lines.push(
        `<details>`,
        `<summary>${status} **${mr.model}** — $${mr.cost.toFixed(5)} | ${mr.wall_time_ms}ms | ${mr.input_tokens}+${mr.output_tokens} tokens</summary>`,
        "",
      );
      if (mr.error) {
        lines.push(`> **Error:** ${mr.error}`, "");
      }
      if (mr.response) {
        lines.push(mr.response, "");
      }
      lines.push("</details>", "");
    }
  }

  // Timed-out models
  if (result.timed_out_models && result.timed_out_models.length > 0) {
    lines.push(
      `⚠️ **Timed-out models:** ${result.timed_out_models.join(", ")}`,
      "",
    );
  }

  // Fused answer (prominent)
  lines.push(
    "---",
    "",
    "## 🧬 Fused Answer",
    "",
    result.fused_answer,
    "",
    "---",
    "",
  );

  // Cost breakdown
  lines.push("## 💰 Cost Breakdown", "");
  for (const mr of result.model_responses) {
    lines.push(
      `- **${mr.model}:** $${mr.cost.toFixed(5)} (${mr.input_tokens}+${mr.output_tokens} tokens, ${mr.wall_time_ms}ms)`,
    );
  }
  lines.push(`- **Total:** $${result.cost.toFixed(5)}`, "");

  lines.push(`*Cost ceiling: $0.50 per fusion*`);

  return lines.join("\n");
}

// ── SDK Fusion Dispatch ────────────────────────────────────────────────

/** Model price rates (USD per token, copied from companion/fusion/dispatch.py). */
const MODEL_RATES: Record<string, [number, number]> = {
  "deepseek-v4-pro":   [0.002 / 1_000_000, 0.008 / 1_000_000],
  "deepseek-v4-flash": [0.0002 / 1_000_000, 0.0008 / 1_000_000],
  "deepseek-v3":       [0.001 / 1_000_000, 0.004 / 1_000_000],
  "gpt-4o":           [0.005 / 1_000_000, 0.015 / 1_000_000],
  "claude-sonnet-4":  [0.003 / 1_000_000, 0.015 / 1_000_000],
  "deepseek-chat":    [0.002 / 1_000_000, 0.008 / 1_000_000],
  "deepseek-reasoner": [0.002 / 1_000_000, 0.008 / 1_000_000],
};

/** Rough token count — ~4 chars per token for English text. */
function approxTokens(text: string): number {
  return Math.max(1, Math.ceil(text.length / 4));
}

function estimateCost(model: string, inputTokens: number, outputTokens: number): number {
  const rates = MODEL_RATES[model] ?? [0, 0];
  return inputTokens * rates[0] + outputTokens * rates[1];
}

function modelProviderId(modelId: string): string {
  if (modelId.startsWith("deepseek")) return "deepseek";
  if (modelId.startsWith("gpt")) return "openai";
  if (modelId.startsWith("claude")) return "anthropic";
  return "deepseek";
}

const SYNTHESIS_PROMPT_TEMPLATE =
  "You are a synthesis engine. Given these {n} responses to the original prompt, " +
  "produce the best combined answer. Consider different perspectives, " +
  "resolve contradictions, and merge complementary insights into a single " +
  "coherent response.\n\n" +
  "--- ORIGINAL PROMPT ---\n{prompt}\n--- END ORIGINAL PROMPT ---\n\n" +
  "{responses}\n\n" +
  "--- SYNTHESIS INSTRUCTIONS ---\n" +
  "1. Identify the strongest claims and evidence from each response.\n" +
  "2. Note any disagreements and explain which position has better support.\n" +
  "3. If one response is noticeably weaker, give it less weight.\n" +
  "4. Produce one unified answer — do NOT present a list of competing answers.\n" +
  "5. Start your response with: {label}\n";

const FUSION_LABEL = "EXPERIMENTAL — Model Fusion (v1-alpha)";
const DEFAULT_FUSION_MODELS = ["deepseek-v4-pro", "deepseek-v4-flash"];
const MAX_FUSION_MODELS = 3;
const DEFAULT_COST_CEILING = 0.50;
const TIMEOUT_PER_MODEL_MS = 60_000;
const POLL_INTERVAL_MS = 500;

interface SessionClient {
  create(body?: Record<string, unknown>): Promise<{ data?: { id: string } }>;
  prompt(input: {
    path?: { id?: string };
    body?: Record<string, unknown>;
  }): Promise<unknown>;
  messages(input: {
    path?: { id?: string };
    query?: Record<string, unknown>;
  }): Promise<{
    data?: Array<{
      info?: { role?: string };
      parts?: Array<{ type?: string; text?: string }>;
    }>;
  }>;
  delete(input: { path?: { id?: string } }): Promise<unknown>;
}

async function pollForResponse(
  sessionClient: SessionClient,
  sessionId: string,
  timeoutMs: number,
): Promise<string> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const msgs = await sessionClient.messages({
      path: { id: sessionId },
      query: { limit: 10 },
    });
    const data = msgs.data ?? [];
    for (let i = data.length - 1; i >= 0; i--) {
      const msg = data[i];
      if (msg.info?.role === "assistant") {
        const text = msg.parts
          ?.filter((p) => p.type === "text" && p.text)
          ?.map((p) => p.text!)
          ?.join("\n");
        if (text) return text;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
  return "";
}

async function sdkFusionDispatch(
  client: { session: SessionClient },
  prompt: string,
  models?: string[],
  synthesisModel?: string,
  costCeiling?: number,
): Promise<FusionResult> {
  const resolvedModels = (models?.length ? models.slice(0, MAX_FUSION_MODELS) : null)
    ?? DEFAULT_FUSION_MODELS;
  const resolvedSynthesisModel = synthesisModel ?? "deepseek-v4-pro";
  const resolvedCostCeiling = costCeiling ?? DEFAULT_COST_CEILING;
  const wallStart = Date.now();
  const tempSessionIds: string[] = [];

  try {
    // ── Phase 1: parallel dispatch ───────────────────────────────────
    const dispatchPromises = resolvedModels.map(async (model) => {
      const t0 = Date.now();
      const inputTokens = approxTokens(prompt);
      let sessionId: string | null = null;

      try {
        const providerID = modelProviderId(model);
        const createResult = await client.session.create({
          body: { model: { id: model, providerID } },
        });
        sessionId = (createResult as any).data?.id;
        if (!sessionId) throw new Error("Failed to create session");
        tempSessionIds.push(sessionId);

        await client.session.prompt({
          path: { id: sessionId },
          body: {
            parts: [{ type: "text", text: prompt }],
            model: { providerID, modelID: model },
          },
        });

        const responseText = await pollForResponse(
          client.session,
          sessionId,
          TIMEOUT_PER_MODEL_MS,
        );

        const wallMs = Date.now() - t0;
        const outputTokens = responseText ? approxTokens(responseText) : 0;
        const cost = responseText ? estimateCost(model, inputTokens, outputTokens) : 0;
        const timedOut = !responseText;

        return {
          model,
          response: responseText,
          cost,
          input_tokens: inputTokens,
          output_tokens: timedOut ? 0 : outputTokens,
          wall_time_ms: wallMs,
          timed_out: timedOut,
          error: timedOut ? "Timeout waiting for response" : null,
        };
      } catch (err) {
        const wallMs = Date.now() - t0;
        return {
          model,
          response: "",
          cost: 0,
          input_tokens: inputTokens,
          output_tokens: 0,
          wall_time_ms: wallMs,
          timed_out: true,
          error: err instanceof Error ? err.message : String(err),
        };
      }
    });

    const results = await Promise.allSettled(dispatchPromises);

    const modelResponses = results.map((r) =>
      r.status === "fulfilled" ? r.value : {
        model: "unknown",
        response: "",
        cost: 0,
        input_tokens: 0,
        output_tokens: 0,
        wall_time_ms: 0,
        timed_out: true,
        error: String(r.reason),
      },
    );

    const successful = modelResponses.filter((r) => !r.timed_out && r.response);
    const timedOutModels = modelResponses
      .filter((r) => r.timed_out)
      .map((r) => r.model);
    const cumulativeCost = modelResponses.reduce((sum, r) => sum + r.cost, 0);

    // ── Phase 2: synthesis ───────────────────────────────────────────
    let fusedAnswer: string;
    let synthCost = 0;

    if (successful.length > 0) {
      try {
        const synthPrompts = successful.map(
          (r, i) => `=== RESPONSE ${i + 1} (from ${r.model}) ===\n${r.response}\n`,
        );
        const synthesisPrompt = SYNTHESIS_PROMPT_TEMPLATE
          .replace("{n}", String(successful.length))
          .replace("{prompt}", prompt)
          .replace("{responses}", synthPrompts.join("\n"))
          .replace("{label}", FUSION_LABEL);

        const synthProviderID = modelProviderId(resolvedSynthesisModel);
        const synthCreateResult = await client.session.create({
          body: {
            model: { id: resolvedSynthesisModel, providerID: synthProviderID },
          },
        });
        const synthSessionId = (synthCreateResult as any).data?.id;
        if (!synthSessionId) throw new Error("Failed to create synthesis session");
        tempSessionIds.push(synthSessionId);

        await client.session.prompt({
          path: { id: synthSessionId },
          body: {
            parts: [{ type: "text", text: synthesisPrompt }],
            model: { providerID: synthProviderID, modelID: resolvedSynthesisModel },
          },
        });

        const synthResponse = await pollForResponse(
          client.session,
          synthSessionId,
          TIMEOUT_PER_MODEL_MS * 2,
        );

        if (synthResponse) {
          synthCost = estimateCost(
            resolvedSynthesisModel,
            approxTokens(synthesisPrompt),
            approxTokens(synthResponse),
          );
          fusedAnswer = synthResponse.includes(FUSION_LABEL)
            ? synthResponse
            : `${FUSION_LABEL}\n\n${synthResponse}`;
        } else {
          fusedAnswer = `${FUSION_LABEL}\n\nFusion synthesis failed: timeout waiting for synthesis model.`;
        }
      } catch (err) {
        fusedAnswer =
          `Fusion synthesis failed: ${err instanceof Error ? err.message : String(err)}`;
      }
    } else {
      fusedAnswer =
        `${FUSION_LABEL}\n\nFusion failed: all models timed out or returned empty responses.`;
    }

    const totalCost = cumulativeCost + synthCost;
    const wallMs = Date.now() - wallStart;

    return {
      prompt,
      model_responses: modelResponses,
      fused_answer: fusedAnswer,
      cost: Math.round(totalCost * 1e6) / 1e6,
      wall_time_ms: wallMs,
      timed_out_models: timedOutModels.length > 0 ? timedOutModels : undefined,
      label: FUSION_LABEL,
    };
  } finally {
    // ── Clean up ALL temp sessions ────────────────────────────────────
    for (const sid of tempSessionIds) {
      try {
        await client.session.delete({ path: { id: sid } });
      } catch (err) {
        logger.warn(`[bifrost] failed to delete temp session ${sid}:`, err);
      }
    }
  }
}

// ── Goal Loop helpers ──────────────────────────────────────────────────

function formatGoalUsage(): string {
  return [
    "╔══════════════════════════════════════════════════════════════╗",
    "║  🎯  Goal Loop — Classifier-Gated Agent Simulation          ║",
    "╚══════════════════════════════════════════════════════════════╝",
    "",
    "**Usage:** `/goal \"your goal description\"`",
    "",
    "Runs a simulated agent loop through the security classifier.",
    "Each action is classified as ALLOW/DENY/ASK_USER. Terminates on:",
    "- Goal achieved (task_done action)",
    "- Max turns reached (default: 10, max: 50)",
    "- Cost ceiling exceeded (default: $1.00)",
    "- 3 consecutive DENY decisions (blocked)",
    "",
    "**Examples:**",
    "```",
    '/goal "Fix all lint errors"',
    '/goal "Add dark mode support"',
    "```",
  ].join("\n");
}

function formatGoalOutput(result: GoalLoopResult): string {
  const lines: string[] = [];

  lines.push(
    "╔══════════════════════════════════════════════════════════════╗",
    "║  🎯  Goal Loop — Classifier-Gated Agent Simulation          ║",
    "╚══════════════════════════════════════════════════════════════╝",
    "",
    `**Goal:** ${result.goal}`,
    "",
  );

  const lastAction =
    result.turns.length > 0
      ? result.turns[result.turns.length - 1].tool_name
      : "none";
  const decisions =
    result.turns.map((t) => t.decision).join(", ") || "none";

  lines.push(
    "## 📊 Progress",
    "",
    `- **Turns used:** ${result.turns_used}`,
    `- **Last action:** ${lastAction}`,
    `- **Classifier decisions:** ${decisions}`,
    "",
  );

  if (result.turns.length > 0) {
    lines.push("### Turn-by-Turn", "");
    lines.push("| # | Action | Decision | Reason |");
    lines.push("|---|--------|----------|--------|");
    for (const t of result.turns) {
      const reason =
        t.reason.length > 60 ? t.reason.slice(0, 57) + "..." : t.reason;
      lines.push(
        `| ${t.turn_index + 1} | ${t.tool_name} | ${t.decision} | ${reason} |`,
      );
    }
    lines.push("");
  }

  const statusIcon =
    result.status === "goal_met"
      ? "✅"
      : result.status === "blocked"
        ? "🚫"
        : result.status === "cost_exceeded"
          ? "💰"
          : "⏱️";

  lines.push(
    "---",
    "",
    "## 📋 Summary",
    "",
    `- **Status:** ${statusIcon} ${result.status}`,
    `- **Turns used:** ${result.turns_used}`,
    `- **Total cost:** $${result.total_cost.toFixed(4)}`,
    `- **Wall time:** ${result.wall_time_ms}ms`,
    `- **Termination:** ${result.termination_reason}`,
  );

  return lines.join("\n");
}

// ── Plugin ─────────────────────────────────────────────────────────────

export default async function bifrostPlugin(
  pluginInput: PluginInput,
  _options?: PluginOptions,
): Promise<Hooks> {
  // Install global fusion skill on every plugin load — idempotent, non-fatal
  installGlobalFusionSkill();

  const relay = new MCPRelay();
  const { client } = pluginInput;
  const monitor = new HealthMonitor(relay);

  try {
    await relay.connect(undefined, COMPANION_SCRIPT);
    monitor.start();
  } catch (err) {
    logger.warn("[bifrost] companion not available (non-fatal):", err);
  }

  return {
    dispose: async () => {
      monitor.stop();
      try {
        await relay.disconnect();
      } catch (err) {
        logger.warn("[bifrost] error disconnecting from companion:", err);
      }
    },

    event: async (evt) => {
      try {
        if (evt.event.type === "session.created") {
          logger.log("[bifrost] session created:", evt.event.properties.info);
        }
      } catch (err) {
        logger.warn("[bifrost] event hook error (non-fatal):", err);
      }
    },

    "tool.execute.before": async (evt, output) => {
      // ── Pre-filter: skip companion entirely for read-only tools ──────
      if (READ_ONLY_TOOLS.has(evt.tool)) {
        return; // ALLOW — tool executes normally, saves ~1586ms latency
      }

      try {
        // ── Call companion classifier via async MCP relay ──────────────
        const result = await monitor.call<ClassifierResult>(
          "classify_tool_call",
          {
            tool_name: evt.tool,
            tool_args: (evt as any).args ?? {},
            file_paths: extractFilePaths(evt.tool, (evt as any).args),
            session_context: buildSessionContext(evt as any),
          },
          15_000, // generous timeout — classifier p95 is ~1586ms
        );

        // ── Handle classification decision ─────────────────────────────
        // ALL decisions show as chat messages via output.allow/output.reason
        switch (result.decision) {
          case "ALLOW":
            (output as any).allow = true;
            (output as any).reason =
              result.reason || `${evt.tool} allowed by classifier`;
            return;

          case "DENY":
            (output as any).allow = false;
            (output as any).reason =
              result.reason || `Tool blocked: ${evt.tool}`;
            return;

          case "ASK_USER":
          default:
            // Unknown/invalid decision → safe fallback to ASK_USER
            (output as any).allow = false;
            (output as any).reason =
              result.reason ||
              `[bifrost] User confirmation required for: ${evt.tool}`;
            return;
        }
      } catch (err) {
        // ── Relay error, timeout, or companion unreachable ─────────────
        // Show classifier unavailable message as chat message
        (output as any).allow = false;
        (output as any).reason =
          `[bifrost] Classifier unavailable — user confirmation required for: ${evt.tool}`;
      }
    },

    "permission.ask": async (_evt, output) => {
      try {
        output.status = "ask";
      } catch (err) {
        logger.warn("[bifrost] permission.ask error (non-fatal):", err);
      }
    },

    // ── fusion tool (AI-invokable, also backing /fusion slash command) ──
    tool: {
      fusion: tool({
        description:
          "EXPERIMENTAL — Model Fusion (v1-alpha). Dispatch a prompt to 2-3 AI models in parallel and synthesize a fused answer. User-invoked only via /fusion slash command.",
        args: {
          prompt: tool.schema
            .string()
            .describe("The prompt to send to all models"),
          models: tool.schema
            .array(tool.schema.string())
            .optional()
            .describe(
              "Model IDs (max 3). Default: deepseek-v4-pro + deepseek-v4-flash",
            ),
          synthesis_model: tool.schema
            .string()
            .optional()
            .describe(
              "Model to use for synthesis. Default: deepseek-v4-pro",
            ),
          cost_ceiling: tool.schema
            .number()
            .optional()
            .describe("Maximum USD cost. Default: $0.50"),
        },
        async execute(args, _context) {
          try {
            const result = await sdkFusionDispatch(
              client,
              args.prompt,
              args.models ?? undefined,
              args.synthesis_model ?? undefined,
              args.cost_ceiling ?? 0.5,
            );
            return formatFusionOutput(result);
          } catch (_sdkErr) {
            if (!relay.connected) {
              return "❌ /fusion failed: SDK dispatch error and companion is not running.";
            }
            try {
              const result = await monitor.call<FusionResult>(
                "fusion_dispatch_tool",
                {
                  prompt: args.prompt,
                  models: args.models ?? undefined,
                  synthesis_model: args.synthesis_model ?? undefined,
                  cost_ceiling: args.cost_ceiling ?? 0.5,
                },
                120_000,
              );
              return formatFusionOutput(result);
            } catch (err) {
              const msg = err instanceof Error ? err.message : String(err);
              return `❌ /fusion failed: ${msg}`;
            }
          }
        },
      }),
    },

    "command.execute.before": async (input, output) => {
      try {
        // ── /fusion ────────────────────────────────────────────────────
        if (input.command === "fusion") {
          const rawArgs = (input.arguments ?? "").trim();
          const prompt = parseFusionArgs(rawArgs);

          if (!prompt) {
            output.parts = [
              { type: "text" as const, text: formatUsage() },
            ] as never;
            return;
          }

          const fusionText = await (async (): Promise<string> => {
            try {
              const result = await sdkFusionDispatch(
                client,
                prompt,
                undefined,
                undefined,
                0.5,
              );
              return formatFusionOutput(result);
            } catch (_sdkErr) {
              if (!relay.connected) {
                return "❌ /fusion failed: SDK dispatch error and companion is not running.";
              }
              try {
                const result = await monitor.call<FusionResult>(
                  "fusion_dispatch_tool",
                  { prompt, cost_ceiling: 0.5 },
                  120_000,
                );
                return formatFusionOutput(result);
              } catch (err) {
                const msg = err instanceof Error ? err.message : String(err);
                return `❌ /fusion failed: ${msg}`;
              }
            }
          })();

          output.parts = [
            { type: "text" as const, text: fusionText },
          ] as never;
          return;
        }

        // ── /goal ────────────────────────────────────────────────────
        if (input.command === "goal") {
          const rawArgs = (input.arguments ?? "").trim();
          const goal = parseFusionArgs(rawArgs);

          if (!goal) {
            output.parts = [
              { type: "text" as const, text: formatGoalUsage() },
            ] as never;
            return;
          }

          if (!relay.connected) {
            output.parts = [
              {
                type: "text" as const,
                text: "❌ Bifrost companion is not running. Start `bifrost-companion` to use `/goal`.",
              },
            ] as never;
            return;
          }

          try {
            const result = await monitor.call<GoalLoopResult>(
              "goal_loop",
              {
                goal,
                actions: [
                  {
                    tool_name: "Read",
                    tool_args: {},
                    estimated_cost: 0.01,
                  },
                ],
              },
              30_000,
            );
            output.parts = [
              {
                type: "text" as const,
                text: formatGoalOutput(result),
              },
            ] as never;
          } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            output.parts = [
              {
                type: "text" as const,
                text: `❌ /goal failed: ${msg}`,
              },
            ] as never;
          }
          return;
        }

        // ── /review ──────────────────────────────────────────────────
        if (input.command === "review") {
          if (!relay.connected) {
            output.parts = [
              {
                type: "text" as const,
                text: "❌ Bifrost companion is not running. Start `bifrost-companion` to use `/review`.",
              },
            ] as never;
            return;
          }

          try {
            const result = await monitor.call<string>("skill_load", {
              name: "review",
              arguments: {},
            });
            output.parts = [
              {
                type: "text" as const,
                text: `🔍 /review — loaded \`review\` skill\n\n${result}`,
              },
            ] as never;
          } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            output.parts = [
              {
                type: "text" as const,
                text: `❌ /review failed: ${msg}`,
              },
            ] as never;
          }
          return;
        }

        // ── /explain ──────────────────────────────────────────────────
        if (input.command === "explain") {
          const rawArgs = (input.arguments ?? "").trim();
          if (!rawArgs) {
            output.parts = [
              {
                type: "text" as const,
                text: "**Usage:** `/explain <file path or code snippet>` — get an AI explanation of the code.",
              },
            ] as never;
            return;
          }
          try {
            const result = await sdkFusionDispatch(
              client,
              `Explain the following code clearly and concisely:\n\n${rawArgs}`,
              ["deepseek-v4-pro"],
              undefined,
              0.1,
            );
            output.parts = [
              {
                type: "text" as const,
                text: `**📖 Code Explanation**\n\n${result.fused_answer}`,
              },
            ] as never;
          } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            output.parts = [
              {
                type: "text" as const,
                text: `❌ /explain failed: ${msg}`,
              },
            ] as never;
          }
          return;
        }

        // ── /commit ──────────────────────────────────────────────────
        if (input.command === "commit") {
          if (!relay.connected) {
            output.parts = [
              {
                type: "text" as const,
                text: "❌ Bifrost companion is not running. Start `bifrost-companion` to use `/commit`.",
              },
            ] as never;
            return;
          }

          try {
            const result = await monitor.call<string>("skill_load", {
              name: "git-master",
              arguments: {},
            });
            output.parts = [
              {
                type: "text" as const,
                text: `📝 /commit — loaded \`git-master\` skill\n\n${result}`,
              },
            ] as never;
          } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            output.parts = [
              {
                type: "text" as const,
                text: `❌ /commit failed: ${msg}`,
              },
            ] as never;
          }
          return;
        }

        // ── /test ──────────────────────────────────────────────────
        if (input.command === "test") {
          if (!relay.connected) {
            output.parts = [
              {
                type: "text" as const,
                text: "❌ Bifrost companion is not running. Start `bifrost-companion` to use `/test`.",
              },
            ] as never;
            return;
          }

          try {
            const result = await monitor.call<string>("skill_load", {
              name: "tdd",
              arguments: {},
            });
            output.parts = [
              {
                type: "text" as const,
                text: `🧪 /test — loaded \`tdd\` skill\n\n${result}`,
              },
            ] as never;
          } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            output.parts = [
              {
                type: "text" as const,
                text: `❌ /test failed: ${msg}`,
              },
            ] as never;
          }
          return;
        }

        // ── /audit-permissions ─────────────────────────────────────────
        if (input.command === "audit-permissions") {
          const arg = (input.arguments ?? "").trim();
          const sourcePath = arg || "~/.claude/settings.json";

          if (!relay.connected) {
            output.parts = [{
              type: "text",
              text: "⚠️  Bifrost companion is not running. Start the companion server to use /audit-permissions.",
            }] as never;
            return;
          }

          const result = await monitor.call<string>("config_migrate", {
            source_path: sourcePath,
          });

          const isToolError =
            typeof result === "string" &&
            (result.startsWith("No Claude Code config found at") ||
              result.startsWith("Error reading") ||
              result.startsWith("Error parsing"));

          if (isToolError) {
            output.parts = [{ type: "text", text: `❌ ${result}` }] as never;
            return;
          }

          const formatted = [
            "╔══════════════════════════════════════════════════════════════╗",
            "║  ⚠️  DO NOT AUTO-APPLY — REVIEW MANUALLY                   ║",
            "║  This is a READ-ONLY audit. Copy sections you need.         ║",
            "╚══════════════════════════════════════════════════════════════╝",
            "",
            result,
            "",
            "──────────────────────────────────────────────────────────────",
            "⚠️  REMINDER: Review each section manually before applying.",
            "   This tool does NOT modify any files.",
          ].join("\n");

          output.parts = [{ type: "text", text: formatted }] as never;
          return;
        }

        // ── Default: unknown command ──────────────────────────────────
        output.parts = [
          {
            type: "text" as const,
            text: `Unknown command: ${input.command}. Available commands: fusion, goal, review, explain, commit, test, audit-permissions`,
          },
        ] as never;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        output.parts = [
          {
            type: "text" as const,
            text: `❌ Command failed: ${msg}`,
          },
        ] as never;
      }
    },

    // ── slash command interception via chat.message (OpenCode routes user-typed
    //    /fusion and /goal through this hook, NOT command.execute.before) ──
    "chat.message": async (input, output) => {
      const text = (output.parts?.find(p => p.type === "text") as any)?.text ?? "";
      if (!text.startsWith("/fusion") && !text.startsWith("/goal")) return;

      try {
        if (text.startsWith("/fusion")) {
          const rawArgs = text.slice("/fusion".length).trim();
          const prompt = rawArgs.replace(/^["']|["']$/g, "").trim();
          if (!prompt) {
            output.parts = [{ type: "text" as const, text: formatUsage() }] as never;
            return;
          }
          const result = await sdkFusionDispatch(client, prompt, undefined, undefined, 0.5);
          output.parts = [{ type: "text" as const, text: formatFusionOutput(result) }] as never;
          return;
        }

        if (text.startsWith("/goal")) {
          const rawArgs = text.slice("/goal".length).trim();
          const goal = rawArgs.replace(/^["']|["']$/g, "").trim();
          if (!goal) {
            output.parts = [{ type: "text" as const, text: formatGoalUsage() }] as never;
            return;
          }
          if (!relay.connected) {
            output.parts = [{ type: "text" as const, text: "❌ Bifrost companion is not running to use `/goal`." }] as never;
            return;
          }
          const result = await monitor.call<GoalLoopResult>("goal_loop", {
            goal, actions: [{ tool_name: "Read", tool_args: {}, estimated_cost: 0.01 }],
          }, 30_000);
          output.parts = [{ type: "text" as const, text: formatGoalOutput(result) }] as never;
          return;
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        output.parts = [{ type: "text" as const, text: `❌ Command failed: ${msg}` }] as never;
      }
    },

    "experimental.session.compacting": async (evt, output) => {
      try {
        logger.log("[bifrost] session compacting:", evt.sessionID);

        if (!relay.connected) return;

        const res = await client.session.messages({
          path: { id: evt.sessionID },
          query: { limit: 10 },
        });

        if (!res.data?.length) return;

        const parts: string[] = [];
        for (const msg of res.data) {
          for (const p of msg.parts) {
            if (p.type === "text" && "text" in p && p.text) {
              parts.push(`[${msg.info.role}] ${p.text}`);
            }
          }
        }

        const raw = parts.join("\n\n").slice(0, 2000);
        if (!raw) return;

        await monitor.call("memory_save", {
          type: "decision",
          content: raw,
          scope: "project",
          project_hash: "",
        });

        logger.log("[bifrost] auto-saved decision memory on compacting");
      } catch (err) {
        logger.warn("[bifrost] experimental.session.compacting error (non-fatal):", err);
      }
    },

    "tool.execute.after": async (evt) => {
      try {
        const e = evt as any;
        const elapsed = e.elapsedMs ?? 0;
        const error = e.error;
        const status = error ? "FAIL" : "OK";
        logger.log(
          `[bifrost] tool.execute.after ${evt.tool} → ${status} (${elapsed}ms)`,
        );

        if (relay.connected && error) {
          await monitor.call("memory_save", {
            type: "feedback",
            content: `Tool ${evt.tool} failed: ${String(error).slice(0, 500)}`,
            scope: "project",
            project_hash: "",
          });
        }
      } catch (err) {
        logger.warn("[bifrost] tool.execute.after error (non-fatal):", err);
      }
    },
  };
}
