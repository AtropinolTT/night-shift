import { MCPRelay, ConnectionError } from "./mcp-relay.js";
import { logger } from "./logger.js";

export interface HealthCheckConfig {
  intervalMs: number;
  failureThreshold: number;
  maxRestarts: number;
  healthCheckTool: string;
  healthCheckArgs: Record<string, unknown>;
}

const DEFAULT_CONFIG: HealthCheckConfig = {
  intervalMs: 30_000,
  failureThreshold: 3,
  maxRestarts: 3,
  healthCheckTool: "echo",
  healthCheckArgs: { message: "ping" },
};

interface QueuedCall {
  tool: string;
  args: Record<string, unknown>;
  timeoutMs: number;
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
}

export class HealthMonitor {
  private relay: MCPRelay;
  private config: HealthCheckConfig;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private consecutiveFailures = 0;
  private restartsThisSession = 0;
  private _restarting = false;
  private queue: QueuedCall[] = [];
  private running = false;

  get connected(): boolean {
    return this.relay.connected && !this._restarting;
  }

  constructor(relay: MCPRelay, config?: Partial<HealthCheckConfig>) {
    this.relay = relay;
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.scheduleNext();
  }

  stop(): void {
    this.running = false;
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  async call<T = unknown>(
    tool: string,
    args: Record<string, unknown> = {},
    timeoutMs = 10_000,
  ): Promise<T> {
    if (this._restarting) {
      return new Promise<T>((resolve, reject) => {
        this.queue.push({
          tool,
          args,
          timeoutMs,
          resolve: resolve as (value: unknown) => void,
          reject,
        });
      });
    }
    return this.relay.call<T>(tool, args, timeoutMs);
  }

  private scheduleNext(): void {
    if (!this.running) return;
    this.timer = setTimeout(() => {
      this.runCheck();
    }, this.config.intervalMs);
  }

  private async runCheck(): Promise<void> {
    if (!this.running) return;

    try {
      await this.relay.call(
        this.config.healthCheckTool,
        this.config.healthCheckArgs,
      );
      this.consecutiveFailures = 0;
    } catch (err) {
      this.consecutiveFailures++;
      logger.warn(
        `[health] check #${this.consecutiveFailures} failed: ${(err as Error).message}`,
      );

      if (this.consecutiveFailures >= this.config.failureThreshold) {
        await this.restart();
      }
    } finally {
      this.scheduleNext();
    }
  }

  private async restart(): Promise<void> {
    if (this.restartsThisSession >= this.config.maxRestarts) {
      logger.error(
        `[health] max restarts (${this.config.maxRestarts}) reached — not retrying`,
      );
      return;
    }

    this._restarting = true;
    this.restartsThisSession++;

    const drained = this.relay.drainPending();
    for (const pending of drained) {
      if (pending.method === "tools/call") {
        const p = pending.params;
        this.queue.push({
          tool: (p.name ?? pending.method) as string,
          args: (p.arguments as Record<string, unknown>) ?? {},
          timeoutMs: pending.timeoutMs ?? 10_000,
          resolve: pending.resolve,
          reject: pending.reject,
        });
      } else {
        pending.reject(new ConnectionError("companion restarting"));
      }
    }

    try {
      await this.relay.disconnect();
      await this.relay.connect(
        this.relay.companionPythonPath,
        this.relay.companionScriptPath,
      );
      this.consecutiveFailures = 0;
      logger.log(
        `[health] restart #${this.restartsThisSession} completed`,
      );
    } catch (err) {
      logger.error(
        `[health] restart #${this.restartsThisSession} failed: ${(err as Error).message}`,
      );
      const failQueue = this.queue.splice(0);
      for (const call of failQueue) {
        call.reject(
          new ConnectionError(
            `companion restart failed: ${(err as Error).message}`,
          ),
        );
      }
      this._restarting = false;
      return;
    }

    const replayQueue = this.queue.splice(0);
    for (const call of replayQueue) {
      this.relay.call(call.tool, call.args, call.timeoutMs).then(call.resolve).catch(call.reject);
    }
    this._restarting = false;
  }
}
