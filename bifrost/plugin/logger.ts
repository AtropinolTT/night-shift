import { appendFileSync, mkdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

const LOG_DIR = join(homedir(), ".bifrost", "logs");
const LOG_FILE = join(LOG_DIR, "plugin.log");

function ensureLogDir(): void {
  if (!existsSync(LOG_DIR)) {
    mkdirSync(LOG_DIR, { recursive: true });
  }
}

function formatTimestamp(): string {
  return new Date().toISOString();
}

export const logger = {
  log: (message: string, ...args: unknown[]) => {
    try {
      ensureLogDir();
      const extra = args.length ? " " + args.map(a => typeof a === "object" ? JSON.stringify(a) : String(a)).join(" ") : "";
      appendFileSync(LOG_FILE, `[${formatTimestamp()}] [LOG] ${message}${extra}\n`);
    } catch {
      // Silently fail if we can't write to log file
    }
  },
  warn: (message: string, ...args: unknown[]) => {
    try {
      ensureLogDir();
      const extra = args.length ? " " + args.map(a => typeof a === "object" ? JSON.stringify(a) : String(a)).join(" ") : "";
      appendFileSync(LOG_FILE, `[${formatTimestamp()}] [WARN] ${message}${extra}\n`);
    } catch {
      // Silently fail
    }
  },
  error: (message: string, ...args: unknown[]) => {
    try {
      ensureLogDir();
      const extra = args.length ? " " + args.map(a => typeof a === "object" ? JSON.stringify(a) : String(a)).join(" ") : "";
      appendFileSync(LOG_FILE, `[${formatTimestamp()}] [ERROR] ${message}${extra}\n`);
    } catch {
      // Silently fail
    }
  },
};
