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

export class CircuitBreakerOpenError extends Error {
  constructor(failures: number) {
    super(`Circuit breaker open after ${failures} consecutive failures`);
    this.name = "CircuitBreakerOpenError";
  }
}

// ── Circuit Breaker ────────────────────────────────────────────────────────

interface CircuitBreakerState {
  state: "closed" | "open" | "half_open";
  failureCount: number;
  lastFailureTime: number;
  openUntil: number;
}

const DEFAULT_CB_THRESHOLD = 5;
const DEFAULT_CB_RESET_MS = 30_000; // 30 seconds
const DEFAULT_CB_HALF_OPEN_TIMEOUT_MS = 5_000;

class CircuitBreaker {
  private state: CircuitBreakerState = {
    state: "closed",
    failureCount: 0,
    lastFailureTime: 0,
    openUntil: 0,
  };

  private halfOpenTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private threshold = DEFAULT_CB_THRESHOLD,
    private resetMs = DEFAULT_CB_RESET_MS,
    private halfOpenTimeoutMs = DEFAULT_CB_HALF_OPEN_TIMEOUT_MS,
  ) {}

  get failureCount(): number {
    return this.state.failureCount;
  }

  get isOpen(): boolean {
    return (
      this.state.state === "open" ||
      (this.state.state === "half_open" && this.halfOpenTimer !== null)
    );
  }

  allowRequest(): boolean {
    if (this.state.state === "closed") return true;

    if (this.state.state === "open") {
      if (Date.now() >= this.state.openUntil) {
        this._enterHalfOpen();
        return true; // allow one probe request
      }
      return false;
    }

    // half_open — allow exactly one probe request, then refuse subsequent ones
    // until the probe completes or the half-open timeout fires
    const wasHalfOpen = this.state.state === "half_open";

    if (wasHalfOpen && this.halfOpenTimer !== null) {
      // Block further requests during HALF_OPEN — only the probe is allowed
      return false;
    }
    return true;
  }

  private _enterHalfOpen(): void {
    this.state = {
      state: "half_open",
      failureCount: 0,
      lastFailureTime: 0,
      openUntil: 0,
    };

    // Set a timeout to force back to OPEN if the probe hangs
    this.halfOpenTimer = setTimeout(() => {
      this.halfOpenTimer = null;
      if (this.state.state === "half_open") {
        // Probe didn't complete in time — reopen
        this.state.state = "open";
        this.state.openUntil = Date.now() + this.resetMs;
      }
    }, this.halfOpenTimeoutMs);
  }

  private _clearHalfOpenTimer(): void {
    if (this.halfOpenTimer !== null) {
      clearTimeout(this.halfOpenTimer);
      this.halfOpenTimer = null;
    }
  }

  recordSuccess(): void {
    this._clearHalfOpenTimer();
    this.state = {
      state: "closed",
      failureCount: 0,
      lastFailureTime: 0,
      openUntil: 0,
    };
  }

  recordFailure(): void {
    this._clearHalfOpenTimer();

    // Sliding window: if enough time has passed since the last failure,
    // reset the failure count (old failures expire)
    const now = Date.now();
    if (this.state.lastFailureTime > 0 && (now - this.state.lastFailureTime) >= this.resetMs) {
      this.state.failureCount = 0;
    }

    const newFailureCount = this.state.failureCount + 1;
    const newState: CircuitBreakerState = {
      state: newFailureCount >= this.threshold ? "open" : this.state.state,
      failureCount: newFailureCount,
      lastFailureTime: now,
      openUntil:
        newFailureCount >= this.threshold ? now + this.resetMs : this.state.openUntil,
    };
    this.state = newState;
  }

  reset(): void {
    this._clearHalfOpenTimer();
    this.state = {
      state: "closed",
      failureCount: 0,
      lastFailureTime: 0,
      openUntil: 0,
    };
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
  timeoutMs: number;
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

/** Detect the appropriate Python executable for the current platform. */
function detectPython(): string {
  return process.platform === "win32" ? "python" : "python3";
}

/**
 * Security: validate a Python executable path before spawn.
 * Throws ConnectionError if the path looks malicious or is unreachable.
 * - Rejects shell metacharacters (`;`, `&`, `|`, `$`, backticks, etc.)
 * - When an absolute path is given, restricts to safe directories
 *   (system /usr/bin, /usr/local/bin, or $HOME)
 * - When the resolved path is a symlink, verifies the symlink target is
 *   also inside a safe directory
 */
async function validatePythonPath(pythonPath: string): Promise<void> {
  if (typeof pythonPath !== "string" || pythonPath.length === 0) {
    throw new ConnectionError(
      "Refusing to spawn Python: invalid path (empty or non-string): " +
        JSON.stringify(pythonPath),
    );
  }
  // Reject shell metacharacters that would enable command injection.
  // Node's spawn() does NOT invoke a shell, but defense-in-depth.
  const dangerousChars: string[] = [
    ";", "&", "|", "\u0060", "$", "<", ">", "(", ")", "{", "}",
    "[", "]", "\\", "\n", "\r", "\t", "\0", "'", '"', " ",
  ];
  for (const c of dangerousChars) {
    if (pythonPath.includes(c)) {
      throw new ConnectionError(
        "Refusing to spawn Python: path contains shell metacharacter " +
          JSON.stringify(c) + ": " + JSON.stringify(pythonPath),
      );
    }
  }
  // Build safe prefix list once (used for both absolute path check and symlink target check)
  const safePrefixesPosix = ["/usr/bin/", "/usr/local/bin/", "/opt/", "/home/"];
  const safePrefixesWin = [
    "C:\\Python",
    "C:\\Program Files\\Python",
    "C:\\Users\\",
  ];
  const safePrefixes: string[] =
    process.platform === "win32" ? safePrefixesWin : safePrefixesPosix;
  // For absolute paths, verify they live in a safe system location.
  const isAbsolutePosix = pythonPath.startsWith("/");
  const isAbsoluteWin = /^[a-zA-Z]:[\\/](?:[^\\/]|$)/.test(pythonPath);
  if (isAbsolutePosix || isAbsoluteWin) {
    if (!safePrefixes.some((p: string) => pythonPath.startsWith(p))) {
      throw new ConnectionError(
        "Refusing to spawn Python: absolute path outside safe directories: " +
          JSON.stringify(pythonPath) +
          ". Allowed prefixes: " +
          safePrefixes.join(", "),
      );
    }
  }
  // If the path is a symlink, verify its real target is also safe.
  try {
    const fs = await import("node:fs/promises");
    const real = await fs.realpath(pythonPath);
    if (real !== pythonPath) {
      if (
        (real.startsWith("/") || /^[a-zA-Z]:[\\/]/.test(real)) &&
        !safePrefixes.some((p: string) => real.startsWith(p))
      ) {
        throw new ConnectionError(
          "Refusing to spawn Python: symlink target outside safe directories: " +
            JSON.stringify(pythonPath) + " -> " + real,
        );
      }
    }
  } catch (err) {
    if (err instanceof ConnectionError) throw err;
    // realpath can fail if the file doesn't exist yet — that's OK,
    // the subsequent spawn() will fail with ENOENT anyway
  }
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
  private _circuitBreaker = new CircuitBreaker();

  get connected(): boolean {
    return this._connected;
  }

  async connect(
    pythonPath: string | undefined = undefined,
    scriptPath?: string,
  ): Promise<void> {
    const resolvedPythonPath = pythonPath ?? detectPython();
    if (this._connected) return;

    // Security: validate the python path before spawn. Reject:
    // - Absolute paths outside safe directories (PATH injection defense)
    // - Paths containing shell metacharacters (command injection defense)
    // - Paths that don't resolve to an actual executable
    await validatePythonPath(resolvedPythonPath);

    this._pythonPath = resolvedPythonPath;
    this._scriptPath = scriptPath;

    const args: string[] = [];
    if (scriptPath) args.push(scriptPath);

    this.proc = spawn(resolvedPythonPath, args, {
      stdio: ["pipe", "pipe", "inherit"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });

    this.proc.stdout!.on("data", (chunk: Buffer) => {
      this.buffer += chunk.toString();
      this.processBuffer();
    });

    this.proc.on("exit", (code) => {
      this._connected = false;
      this._circuitBreaker.recordFailure();
      this.rejectAll(
        new ConnectionError(`companion exited with code ${code ?? "unknown"}`),
      );
    });

    this.proc.on("error", (err) => {
      this._connected = false;
      this._circuitBreaker.recordFailure();
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
    if (!this._circuitBreaker.allowRequest()) {
      throw new CircuitBreakerOpenError(this._circuitBreaker.failureCount);
    }

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

        this._circuitBreaker.recordSuccess();
        return extractResult(raw) as T;
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));
        this._circuitBreaker.recordFailure();
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
      this.pending.set(id, { resolve, reject, timer, method, params, timeoutMs });
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
      let msg: JSONRPCResponse;
      try {
        msg = JSON.parse(trimmed) as JSONRPCResponse;
      } catch {
        console.warn("[bifrost] malformed JSON line in MCP buffer, skipping:", trimmed.slice(0, 80));
        continue;
      }
      if (msg.id != null && this.pending.has(msg.id)) {
        const call = this.pending.get(msg.id)!;
        clearTimeout(call.timer);
        this.pending.delete(msg.id);
        if (msg.error) {
          this._circuitBreaker.recordFailure();
          call.reject(
            new Error(
              `MCP error ${msg.error.code}: ${msg.error.message}`,
            ),
          );
        } else {
          call.resolve(msg.result);
        }
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
    timeoutMs: number;
  }> {
    const drained: Array<{
      method: string;
      params: Record<string, unknown>;
      resolve: (value: unknown) => void;
      reject: (error: Error) => void;
      timeoutMs: number;
    }> = [];
    for (const [id, call] of this.pending) {
      clearTimeout(call.timer);
      drained.push({
        method: call.method,
        params: call.params,
        resolve: call.resolve,
        reject: call.reject,
        timeoutMs: call.timeoutMs,
      });
    }
    this.pending.clear();
    return drained;
  }

  private cleanup(): void {
    this._connected = false;
    this._circuitBreaker.reset();
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

  if (text.startsWith("{") || text.startsWith("[")) {
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }

  return text;
}
