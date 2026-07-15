import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(scriptDir, "..");
const projectRoot = path.resolve(frontendRoot, "..");
const backendDir = path.join(projectRoot, "backend");
const apiHost = process.env.LORECHAT_API_HOST || "127.0.0.1";
const apiPort = Number(process.env.LORECHAT_BACKEND_PORT || 8000);
const devPort = Number(process.env.LORECHAT_FRONTEND_PORT || 5173);
const isWin = process.platform === "win32";
const WIN_CREATE_NEW_PROCESS_GROUP = 0x00000200;
const python = path.join(
  backendDir,
  ".venv",
  isWin ? "Scripts/python.exe" : "bin/python",
);
const vite = path.join(frontendRoot, "node_modules", "vite", "bin", "vite.js");

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function assertPortAvailable(port) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 500);
  try {
    await fetch(`http://${apiHost}:${port}/`, { signal: controller.signal });
    throw new Error(
      `Port ${port} is already in use. Run "lorechat.bat stop" first.`,
    );
  } catch (err) {
    if (err instanceof Error && err.message.includes("already in use")) {
      throw err;
    }
  } finally {
    clearTimeout(timer);
  }
}

async function waitForApiReady(uvicornProc) {
  const url = `http://${apiHost}:${apiPort}/api/tree`;
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (uvicornProc.exitCode !== null) {
      throw new Error(
        `API exited before ready (code ${uvicornProc.exitCode}). Check backend/.env and venv.`,
      );
    }
    try {
      const resp = await fetch(url);
      if (resp.ok) {
        return;
      }
    } catch {
      // retry
    }
    await sleep(500);
  }
  throw new Error(
    `API not ready on http://${apiHost}:${apiPort} after 60s. Run "lorechat.bat stop" then retry.`,
  );
}

/** @type {import("node:child_process").ChildProcess | null} */
let uvicorn = null;
/** @type {import("node:child_process").ChildProcess | null} */
let viteProc = null;

function shutdown(code = 0) {
  for (const proc of [viteProc, uvicorn]) {
    if (proc && !proc.killed && proc.pid) {
      if (isWin) {
        spawn("taskkill", ["/PID", String(proc.pid), "/T", "/F"], { stdio: "ignore" });
      } else {
        proc.kill("SIGTERM");
      }
    }
  }
  process.exit(code);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

if (!fs.existsSync(python)) {
  console.error(`Python not found: ${python}`);
  process.exit(1);
}
if (!fs.existsSync(vite)) {
  console.error(`Vite not found: ${vite}`);
  process.exit(1);
}

try {
  await assertPortAvailable(apiPort);
  await assertPortAvailable(devPort);

  console.log(`[Lore Chat] API   http://${apiHost}:${apiPort}  (uvicorn --reload)`);
  console.log(`[Lore Chat] Vite  http://${apiHost}:${devPort}  (HMR)`);
  console.log("");

  /** @type {import("node:child_process").SpawnOptions} */
  const uvicornOptions = {
    cwd: backendDir,
    stdio: "inherit",
  };
  if (isWin) {
    uvicornOptions.creationFlags = WIN_CREATE_NEW_PROCESS_GROUP;
  }
  uvicorn = spawn(
    python,
    [
      "dev_server.py",
      "--host",
      apiHost,
      "--port",
      String(apiPort),
      "--reload-dir",
      backendDir,
      "--reload-dir",
      path.join(backendDir, "app"),
    ],
    uvicornOptions,
  );

  uvicorn.on("error", (err) => {
    console.error("Failed to start API:", err.message);
    shutdown(1);
  });
  uvicorn.on("exit", (code) => {
    if (code && code !== 0) {
      console.error(`API exited with code ${code}`);
      shutdown(code);
    }
  });

  await waitForApiReady(uvicorn);
  console.log(`[Lore Chat] API ready`);

  viteProc = spawn(
    process.execPath,
    [vite, "--host", "0.0.0.0", "--port", String(devPort)],
    { cwd: frontendRoot, stdio: "inherit" },
  );

  viteProc.on("error", (err) => {
    console.error("Failed to start Vite:", err.message);
    shutdown(1);
  });

  const viteExit = await new Promise((resolve) => {
    viteProc.on("exit", (code) => resolve(code ?? 0));
  });
  shutdown(viteExit);
} catch (err) {
  console.error(err instanceof Error ? err.message : err);
  shutdown(1);
}
