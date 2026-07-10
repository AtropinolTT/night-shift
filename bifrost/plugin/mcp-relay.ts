import { spawn, type ChildProcess } from "node:child_process";

// ── Errors ────────────────────────────────────────────────────────────────

export class ConnectionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConnectionError";
  }
}

export class TimeoutError extends Error {
  constructor(tool: string, ms: number) {
    super(`MCP call "${tool}" timed out after ${ms}ms`);
    this.name = "TimeoutError";
  }
}

// ── Internal wire types ───────────────────────────────────────────────────

interface JSONRPCRequest {
  jsonrpc: "2.0";
  id?: number;
  method: string;
  params?: Record<string, unknown>;
}

interface JSONRPCResponse {
  jsonrpc: "2.0";
  id: number;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

interface PendingCall {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
  timer: NodeJS.Timeout;
  method: string;
  params: Record<string, unknown>;
}

// ── Public result types ───────────────────────────────────────────────────

export interface ToolInfo {
  name: string;
  description?: string;
  inputSchema?: unknown;
}

export interface MemoryEntry {
  id: number;
  type: string;
  content: string;
  scope: string;
  created_at: string;
  rank?: number;
}

export interface MCPContentItem {
  type: string;
  text?: string;
  data?: unknown;
}

export interface ToolCallResult {
  content: MCPContentItem[];
  isError?: boolean;
}

// ── MCPRelay ──────────────────────────────────────────────────────────────

export class MCPRelay {
  private proc: ChildProcess | null = null;
  private pending = new Map<number, PendingCall>();
  private nextId = 1;
  private buffer = "";
  private _connected = false;
  private _pythonPath = "python3";
  private _scriptPath?: string;
  private _maxRetries = 3;
  private _retryDelayMs = 500;
  private _defaultTimeoutMs = 10_000;

  get connected(): boolean {
    return this._connected;
  }

  async connect(
    pythonPath = "python3",
    scriptPath?: string,
  ): Promise<void> {
    if (this._connected) return;

    this._pythonPath = pythonPath;
    this._scriptPath = scriptPath;

    const args: string[] = [];
    if (scriptPath) args.push(scriptPath);

    this.proc = spawn(pythonPath, args, {
      stdio: ["pipe", "pipe", "inherit"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });

    this.proc.stdout!.on("data", (chunk: Buffer) => {
      this.buffer += chunk.toString();
      this.processBuffer();
    });

    this.proc.on("exit", (code) => {
      this._connected = false;
      this.rejectAll(
        new ConnectionError(`companion exited with code ${code ?? "unknown"}`),
      );
    });

    this.proc.on("error", (err) => {
      this._connected = false;
      this.rejectAll(new ConnectionError(err.message));
    });

    try {
      await this.initialize();
      this._connected = true;
    } catch (err) {
      this.cleanup();
      throw err;
    }
  }

  async call<T = unknown>(
    tool: string,
    args: Record<string, unknown> = {},
    timeoutMs = this._defaultTimeoutMs,
  ): Promise<T> {
    let lastError: Error | undefined;

    for (let attempt = 0; attempt <= this._maxRetries; attempt++) {
      if (attempt > 0) {
        await sleep(this._retryDelayMs);
      }

      try {
        const raw = (await this.sendRequest("tools/call", {
          name: tool,
          arguments: args,
        }, timeoutMs)) as ToolCallResult;

        if (raw.isError) {
          throw new Error(
            raw.content?.[0]?.text ?? `tool "${tool}" returned an error`,
          );
        }

        return extractResult(raw) as T;
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));
        if (!shouldRetry(lastError)) break;
      }
    }

    throw lastError ?? new Error(`call "${tool}" failed`);
  }

  async listTools(): Promise<ToolInfo[]> {
    const raw = (await this.sendRequest("tools/list", {})) as {
      tools: ToolInfo[];
    };
    return raw.tools;
  }

  async disconnect(): Promise<void> {
    this.cleanup();
  }

  // ── private ───────────────────────────────────────────────────────────

  private async initialize(): Promise<void> {
    await this.sendRequest("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "bifrost", version: "0.1.0" },
    });

    this.sendNotification("notifications/initialized", {});
  }

  private sendRequest(
    method: string,
    params: Record<string, unknown> = {},
    timeoutMs = this._defaultTimeoutMs,
  ): Promise<unknown> {
    const id = this.nextId++;

    const promise = new Promise<unknown>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new TimeoutError(method, timeoutMs));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer, method, params });
    });

    this.write({ jsonrpc: "2.0", id, method, params });
    return promise;
  }

  private sendNotification(
    method: string,
    params: Record<string, unknown> = {},
  ): void {
    this.write({ jsonrpc: "2.0", method, params });
  }

  private write(msg: JSONRPCRequest): void {
    if (!this.proc?.stdin) {
      throw new ConnectionError("companion not connected");
    }
    this.proc.stdin.write(JSON.stringify(msg) + "\n");
  }

  private processBuffer(): void {
    const lines = this.buffer.split("\n");
    this.buffer = lines.pop() ?? "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const msg = JSON.parse(trimmed) as JSONRPCResponse;
        if (msg.id != null && this.pending.has(msg.id)) {
          const call = this.pending.get(msg.id)!;
          clearTimeout(call.timer);
          this.pending.delete(msg.id);
          if (msg.error) {
            call.reject(
              new Error(
                `MCP error ${msg.error.code}: ${msg.error.message}`,
              ),
            );
          } else {
            call.resolve(msg.result);
          }
        }
      } catch {
        /* skip malformed lines */
      }
    }
  }

  private rejectAll(error: Error): void {
    for (const [id, call] of this.pending) {
      clearTimeout(call.timer);
      call.reject(error);
      this.pending.delete(id);
    }
  }

  get companionPythonPath(): string {
    return this._pythonPath;
  }

  get companionScriptPath(): string | undefined {
    return this._scriptPath;
  }

  /** Drain all pending calls without rejecting them (used during graceful restart). */
  drainPending(): Array<{
    method: string;
    params: Record<string, unknown>;
    resolve: (value: unknown) => void;
    reject: (error: Error) => void;
  }> {
    const drained: Array<{
      method: string;
      params: Record<string, unknown>;
      resolve: (value: unknown) => void;
      reject: (error: Error) => void;
    }> = [];
    for (const [id, call] of this.pending) {
      clearTimeout(call.timer);
      drained.push({
        method: call.method,
        params: call.params,
        resolve: call.resolve,
        reject: call.reject,
      });
    }
    this.pending.clear();
    return drained;
  }

  private cleanup(): void {
    this._connected = false;
    this.rejectAll(new ConnectionError("connection closed"));
    this.proc?.stdin?.end();
    this.proc?.kill();
    this.proc = null;
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function shouldRetry(err: Error): boolean {
  return (
    err instanceof ConnectionError ||
    err instanceof TimeoutError
  );
}

function extractResult(raw: ToolCallResult): unknown {
  if (!raw.content?.length) return null;

  const textItem = raw.content.find((c) => c.type === "text");
  if (!textItem?.text) return raw;

  const text = textItem.text;

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
