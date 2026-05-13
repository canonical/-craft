/**
 * dashcraft Extension for pi
 *
 * The core extension behind `dashcraft` — charming, but fast. Researches a
 * cloned workload and generates a fully populated Juju charm on the fly.
 *
 * Features:
 *   /dashcraft [name]      — scaffold & research a new charm interactively
 *   dashcraft              — tool for the LLM: takes a charm directory + workload clone,
 *                            researches the workload, then writes charmcraft.yaml & src/charm.py
 *   charm_build            — run `quickpack pack` (installs prereqs, then packs)
 *   charm_lint             — run ruff/codespell/pyright via `uv run --group lint`
 *   charm_test_unit        — run pytest via `uv run --group unit`
 *   charm_test_integration — run pytest via `uv run --group integration`
 *   charm_help             — list available skills and reference docs
 *
 * Skills loaded (callable via /skill:<name>):
 *   quick-charm-workflow, relations, charm-testing, observability,
 *   operational-patterns, quality-review, debugging
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Text } from "@earendil-works/pi-tui";
import { Type } from "typebox";
import * as fs from "node:fs";
import * as path from "node:path";
import { execSync, spawn } from "node:child_process";

import {
  allFiles,
  skeletonFiles,
  filledFiles,
  makeContext,
  emptyAnalysis,
  type WorkloadAnalysis,
} from "./templates";

/** Skills shipped with this extension. */
const SKILLS_DIR = path.resolve(__dirname, "..", "..", "skills");

// ── Helpers ─────────────────────────────────────────────────────────────────

/** Check whether `quickpack` is available on PATH. */
function quickpackAvailable(): boolean {
  try {
    execSync("which quickpack", { encoding: "utf-8" });
    return true;
  } catch {
    return false;
  }
}

/** Check whether `dashcraft` is available on PATH. */
function dashcraftAvailable(): boolean {
  try {
    execSync("which dashcraft", { encoding: "utf-8" });
    return true;
  } catch {
    return false;
  }
}

/**
 * Spawn *cmd* with *args*, streaming each output line through *onLine*
 * (typically wired to the tool's `onUpdate` so the CLI can show live
 * progress for long-running commands). Resolves with the full transcript
 * and the exit-code-derived ok flag once the process exits.
 *
 * Handles AbortSignal (SIGTERM) and a millisecond timeout (SIGKILL).
 */
function streamProcess(
  cmd: string,
  args: string[],
  options: {
    cwd: string;
    timeoutMs: number;
    signal?: AbortSignal;
    onLine?: (line: string) => void;
  },
): Promise<{ ok: boolean; output: string }> {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, {
      cwd: options.cwd,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let output = "";
    let stdoutBuf = "";
    let stderrBuf = "";

    const consume = (buf: string, isErr: boolean): string => {
      const lines = buf.split(/\r?\n/);
      const remainder = lines.pop() ?? "";
      for (const line of lines) {
        output += (isErr ? "[stderr] " : "") + line + "\n";
        if (line.trim()) options.onLine?.(line);
      }
      return remainder;
    };

    child.stdout?.on("data", (chunk: Buffer) => {
      stdoutBuf = consume(stdoutBuf + chunk.toString("utf-8"), false);
    });
    child.stderr?.on("data", (chunk: Buffer) => {
      stderrBuf = consume(stderrBuf + chunk.toString("utf-8"), true);
    });

    const timeoutId = setTimeout(() => {
      try { child.kill("SIGKILL"); } catch {}
    }, options.timeoutMs);

    const abortHandler = () => {
      try { child.kill("SIGTERM"); } catch {}
    };
    options.signal?.addEventListener("abort", abortHandler);

    child.on("close", (code) => {
      clearTimeout(timeoutId);
      options.signal?.removeEventListener("abort", abortHandler);
      // Flush trailing partial lines.
      if (stdoutBuf) { output += stdoutBuf + "\n"; if (stdoutBuf.trim()) options.onLine?.(stdoutBuf); }
      if (stderrBuf) { output += "[stderr] " + stderrBuf + "\n"; if (stderrBuf.trim()) options.onLine?.(stderrBuf); }
      resolve({ ok: code === 0, output: output.trim() });
    });
    child.on("error", (err) => {
      clearTimeout(timeoutId);
      options.signal?.removeEventListener("abort", abortHandler);
      output += `[error] ${err.message}\n`;
      resolve({ ok: false, output: output.trim() });
    });
  });
}

/** Run a quickpack command, streaming output line-by-line. */
function runQuickpack(
  args: string[],
  cwd: string,
  options: { timeoutMs?: number; signal?: AbortSignal; onLine?: (line: string) => void },
): Promise<{ ok: boolean; output: string }> {
  return streamProcess("quickpack", args, {
    cwd,
    timeoutMs: options.timeoutMs ?? 300_000,
    signal: options.signal,
    onLine: options.onLine,
  });
}

/** Run a dashcraft CLI command and return { ok, stdout, stderr }. */
function runDashcraft(
  args: string[],
  cwd?: string,
  options?: { timeout?: number; signal?: AbortSignal },
): { ok: boolean; stdout: string; stderr: string } {
  try {
    const output = execSync(`dashcraft ${args.join(" ")}`, {
      cwd,
      encoding: "utf-8",
      timeout: options?.timeout ?? 300_000,
      signal: options?.signal,
      stdio: ["pipe", "pipe", "pipe"],
    });
    return { ok: true, stdout: output.trim(), stderr: "" };
  } catch (err: any) {
    return {
      ok: false,
      stdout: err.stdout || "",
      stderr: err.stderr || err.message || String(err),
    };
  }
}

/**
 * Run `uv <args>` in *cwd*, streaming each output line through *onLine*
 * and resolving with the full transcript + exit-derived ok flag.
 *
 * Used by charm_lint / charm_test_unit / charm_test_integration to bypass
 * tox — `uv run --group <name>` resolves the right dependency group from
 * the generated charm's pyproject.toml without paying tox's per-env venv
 * creation cost on every call.
 */
function runUv(
  args: string[],
  cwd: string,
  timeoutMs: number,
  signal?: AbortSignal,
  onLine?: (line: string) => void,
): Promise<{ ok: boolean; output: string }> {
  return streamProcess("uv", args, { cwd, timeoutMs, signal, onLine });
}

/** Write a file, creating parent directories as needed. */
function writeFile(filePath: string, content: string): void {
  const dir = path.dirname(filePath);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(filePath, content, "utf-8");
}

/** Check if a directory is empty (no files except .git). */
function isDirEmpty(dir: string): boolean {
  const entries = fs.readdirSync(dir).filter((e) => e !== ".git");
  return entries.length === 0;
}

/** Safely scaffold a charm project into targetDir. */
function scaffoldCharm(charmName: string, targetDir: string, skeleton = false): {
  created: string[];
  skipped: string[];
} {
  const ctx = makeContext(charmName);
  const files = skeleton ? skeletonFiles(ctx) : allFiles(ctx);
  const created: string[] = [];
  const skipped: string[] = [];

  for (const [relPath, content] of files) {
    const fullPath = path.join(targetDir, relPath);
    if (fs.existsSync(fullPath)) {
      skipped.push(relPath);
    } else {
      writeFile(fullPath, content);
      created.push(relPath);
    }
  }

  return { created, skipped };
}

// ── Workload analysis ──────────────────────────────────────────────────────

/** Try to read a file; return its content or "" on failure. */
function tryRead(filePath: string): string {
  try {
    return fs.readFileSync(filePath, "utf-8");
  } catch {
    return "";
  }
}

/** Look for a file with one of the given names under baseDir. */
function findFile(baseDir: string, names: string[]): string | null {
  for (const name of names) {
    const p = path.join(baseDir, name);
    if (fs.existsSync(p)) return p;
  }
  return null;
}

/** Extract the first match of a regex from a string. */
function firstMatch(text: string, re: RegExp): string {
  const m = text.match(re);
  return m ? m[1] ?? m[0] : "";
}

/** Parse Dockerfile EXPOSE directives. */
function parseDockerExpose(dockerfile: string): number[] {
  const ports: number[] = [];
  for (const line of dockerfile.split("\n")) {
    const m = line.match(/^\s*EXPOSE\s+(\d+)(?:\/(?:tcp|udp))?/i);
    if (m) ports.push(Number(m[1]));
  }
  return ports;
}

/** Parse Dockerfile ENV directives while skipping ARGs used inside. */
function parseDockerEnv(dockerfile: string): Record<string, string> {
  const env: Record<string, string> = {};
  for (const line of dockerfile.split("\n")) {
    const m = line.match(/^\s*ENV\s+(\w+)\s*=\s*(.+)/i);
    if (m) env[m[1]] = m[2].replace(/"/g, "").trim();
  }
  return env;
}

/** Parse a .env.example or .env file into key=value pairs. */
function parseDotEnv(content: string): Record<string, string> {
  const env: Record<string, string> = {};
  for (const line of content.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq > 0) {
      const key = trimmed.slice(0, eq);
      const val = trimmed.slice(eq + 1).replace(/(^["']|["']$)/g, "");
      env[key] = val;
    }
  }
  return env;
}

/** Extract the first markdown heading from README content. */
function extractReadmeHeading(readme: string): string {
  const m = readme.match(/^#\s+(.+)/m);
  return m ? m[1].replace(/[`*_~]/g, "").trim() : "";
}

/**
 * Research a cloned workload directory and return structured analysis.
 *
 * Heuristics:
 *   - Dockerfile      → command hint, exposed ports, env vars
 *   - package.json    → Node.js detection, start script
 *   - go.mod          → Go detection
 *   - requirements.txt/pyproject.toml → Python detection + framework
 *   - Makefile         → common targets
 *   - .env.example/.env → config options
 *   - docker-compose.yml → services
 *   - README.md        → description
 */
function analyseWorkload(workloadDir: string, charmName: string): WorkloadAnalysis {
  const analysis = emptyAnalysis(charmName);

  // Do we have a Dockerfile?
  const dockerfilePath = findFile(workloadDir, ["Dockerfile", "Dockerfile.prod", "Dockerfile.dev"]);
  if (dockerfilePath) {
    const df = tryRead(dockerfilePath);
    analysis.hasDockerfile = true;

    // EXPOSE
    const exposePorts = parseDockerExpose(df);
    analysis.dockerExposePorts = exposePorts;

    // ENV
    const env = parseDockerEnv(df);
    if (Object.keys(env).length) analysis.envVars = { ...analysis.envVars, ...env };

    // CMD / ENTRYPOINT hint
    const cmdHint =
      firstMatch(df, /^\s*CMD\s+(.+)/im) ||
      firstMatch(df, /^\s*ENTRYPOINT\s+(.+)/im);
    analysis.dockerCmdHint = cmdHint;
  }

  // docker-compose
  const composePath = findFile(workloadDir, ["docker-compose.yml", "docker-compose.yaml"]);
  analysis.hasDockerCompose = !!composePath;
  if (composePath) {
    const compose = tryRead(composePath);
    // Quick parse for environment / ports (best-effort, not a full YAML parser)
    const serviceEnvRe = /^\s{2,}(\w+)\s*[:=]\s*(.+)/gm;
    let match;
    while ((match = serviceEnvRe.exec(compose)) !== null) {
      if (!["image", "ports", "environment", "command", "build", "depends_on", "restart",
             "volumes", "networks", "container_name", "expose", "env_file"].includes(match[1])) {
        // treat unknown top-level keys as env if they look like env vars
      }
    }
    // Look for environment block
    const envBlock = compose.match(/environment:\s*\n((?:\s{4,}[^\n]+\n)*)/);
    if (envBlock) {
      for (const line of envBlock[1].split("\n")) {
        const kv = line.match(/^\s{4,}(\w+)\s*[:=]\s*(.+)/);
        if (kv && !["image", "ports", "command", "build", "depends_on",
                     "restart", "volumes", "networks", "container_name",
                     "expose", "env_file"].includes(kv[1])) {
          analysis.envVars[kv[1]] = kv[2].replace(/"/g, "");
        }
      }
    }
    // Port detection from compose
    const portMatch = compose.match(/"?(\d+):(\d+)"?/);
    if (portMatch) {
      analysis.dockerExposePorts.push(Number(portMatch[2]));
    }
  }

  // Language detection
  if (fs.existsSync(path.join(workloadDir, "package.json"))) {
    analysis.language = "nodejs";
    const pkgJson = JSON.parse(tryRead(path.join(workloadDir, "package.json")));
    if (pkgJson.name) analysis.name = pkgJson.name;
    if (pkgJson.description) {
      analysis.summary = pkgJson.description;
      analysis.description = pkgJson.description;
    }
    // Detect framework
    const deps = { ...pkgJson.dependencies, ...pkgJson.devDependencies };
    if (deps?.express) analysis.framework = "express";
    else if (deps?.next) analysis.framework = "nextjs";
    else if (deps?.fastify) analysis.framework = "fastify";
    else if (deps?.koa) analysis.framework = "koa";
    // Startup command
    if (pkgJson.scripts?.start) analysis.command = `npm start`;
    else if (pkgJson.scripts?.dev) analysis.command = `npm run dev`;
    else if (pkgJson.main) analysis.command = `node ${pkgJson.main}`;
    // Env
    const dotEnvPath = findFile(workloadDir, [".env.example", ".env"]);
    if (dotEnvPath) {
      analysis.envVars = { ...analysis.envVars, ...parseDotEnv(tryRead(dotEnvPath)) };
    }
    // Port from env
    if (analysis.envVars["PORT"]) {
      const portNum = Number(analysis.envVars["PORT"]);
      if (!isNaN(portNum)) analysis.port = portNum;
    }
    analysis.isWebApp = !!deps?.express || !!deps?.next || !!deps?.fastify || !!deps?.koa;
  } else if (fs.existsSync(path.join(workloadDir, "go.mod"))) {
    analysis.language = "go";
    const goMod = tryRead(path.join(workloadDir, "go.mod"));
    const modMatch = goMod.match(/^module\s+(\S+)/m);
    if (modMatch) analysis.name = modMatch[1].split("/").pop() ?? modMatch[1];

    // Check for web frameworks
    if (goMod.includes("gin-gonic/gin") || goMod.includes("labstack/echo") ||
        goMod.includes("gofiber/fiber")) {
      analysis.isWebApp = true;
    }
    analysis.command = `/${analysis.name}`;
  } else if (fs.existsSync(path.join(workloadDir, "requirements.txt")) ||
             fs.existsSync(path.join(workloadDir, "pyproject.toml"))) {
    analysis.language = "python";
    if (fs.existsSync(path.join(workloadDir, "requirements.txt"))) {
      const reqs = tryRead(path.join(workloadDir, "requirements.txt"));
      if (reqs.includes("flask")) analysis.framework = "flask";
      else if (reqs.includes("django")) analysis.framework = "django";
      else if (reqs.includes("fastapi")) analysis.framework = "fastapi";
    }
    if (fs.existsSync(path.join(workloadDir, "pyproject.toml"))) {
      const ppt = tryRead(path.join(workloadDir, "pyproject.toml"));
      if (!analysis.name || analysis.name === charmName) {
        const nameMatch = ppt.match(/^name\s*=\s*"([^"]+)"/m);
        if (nameMatch) analysis.name = nameMatch[1];
      }
      if (!analysis.framework || analysis.framework === "none") {
        if (ppt.includes("flask")) analysis.framework = "flask";
        else if (ppt.includes("django")) analysis.framework = "django";
        else if (ppt.includes("fastapi")) analysis.framework = "fastapi";
      }
    }
    // Startup command
    if (analysis.framework === "flask") {
      analysis.command = "python -m flask run --host=0.0.0.0";
      analysis.port = 5000;
    } else if (analysis.framework === "django") {
      analysis.command = "python manage.py runserver 0.0.0.0:8000";
      analysis.port = 8000;
    } else if (analysis.framework === "fastapi") {
      analysis.command = "uvicorn app.main:app --host 0.0.0.0 --port 8000";
      analysis.port = 8000;
    } else {
      analysis.command = "python -m your_module  # TODO: set startup command";
    }
    analysis.isWebApp = ["flask", "django", "fastapi"].includes(analysis.framework);
  } else if (fs.existsSync(path.join(workloadDir, "Cargo.toml"))) {
    analysis.language = "rust";
    const cargo = tryRead(path.join(workloadDir, "Cargo.toml"));
    const nameMatch = cargo.match(/^name\s*=\s*"([^"]+)"/m);
    if (nameMatch) analysis.name = nameMatch[1];
    analysis.command = `/${analysis.name}`;
  }

  // Dockerfile command overrides guessed command
  if (analysis.dockerCmdHint) {
    analysis.command = analysis.dockerCmdHint;
  }

  // Dockerfile EXPOSE ports override guessed port
  if (analysis.dockerExposePorts.length > 0) {
    analysis.port = analysis.dockerExposePorts[0];
  }

  // README
  const readmePath = findFile(workloadDir, ["README.md", "README.rst"]);
  if (readmePath) {
    const readme = tryRead(readmePath);
    const heading = extractReadmeHeading(readme);
    if (heading && (!analysis.summary || analysis.summary === "Charm for " + charmName)) {
      analysis.summary = heading;
    }
  }

  // If we don't have a good name yet, use charm name
  if (!analysis.name || analysis.name === charmName) {
    analysis.name = charmName;
  }

  // Make sure we have a summary
  if (!analysis.summary) {
    analysis.summary = `Charm for ${analysis.name}`;
  }

  // Build description
  if (!analysis.description) {
    const parts: string[] = [];
    parts.push(`A Juju charm that deploys and manages ${analysis.name}.`);
    if (analysis.language !== "unknown") {
      parts.push(`Built with ${analysis.language}${analysis.framework !== "none" ? " (" + analysis.framework + ")" : ""}.`);
    }
    analysis.description = parts.join(" ");
  }

  // Database detection
  if (analysis.envVars["DATABASE_URL"] || analysis.envVars["DB_URL"] ||
      analysis.envVars["POSTGRES_URL"] || analysis.envVars["DATABASE_HOST"]) {
    analysis.needsDatabase = true;
  }
  if (analysis.envVars["REDIS_URL"] || analysis.envVars["REDIS_HOST"]) {
    analysis.needsCache = true;
  }

  return analysis;
}

// ── Extension ───────────────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  // ── Skill discovery ────────────────────────────────────────────────────

  pi.on("resources_discover", async (_event, _ctx) => {
    return {
      skillPaths: [SKILLS_DIR],
    };
  });

  // ── /dashcraft command ─────────────────────────────────────────────────

  pi.registerCommand("dashcraft", {
    description: "Scaffold a new Juju charm with workload research (dashcraft)",
    async handler(args, ctx) {
      if (!ctx.hasUI) {
        ctx.ui.notify("/dashcraft requires interactive mode", "error");
        return;
      }

      // Step 1: Charm name
      let charmName = args?.trim() || "";
      if (!charmName) {
        charmName = (await ctx.ui.input(
          "Charm name (kebab-case):",
          path.basename(fs.realpathSync(ctx.cwd)),
        )) ?? "";
      }
      if (!charmName || !/^[a-z][a-z0-9-]*$/.test(charmName)) {
        ctx.ui.notify(
          `Invalid charm name "${charmName}". Use kebab-case (e.g. "my-app").`,
          "error",
        );
        return;
      }

      // Step 2: Charm directory
      const charmSubdir = (await ctx.ui.input(
        "Charm project directory:",
        `./${charmName}`,
      )) ?? `./${charmName}`;

      const charmDir = path.resolve(ctx.cwd, charmSubdir);

      // Step 3: Workload directory
      const workloadDefault = `/tmp/${charmName}-workload`;
      const workloadPath = (await ctx.ui.input(
        "Path to cloned workload source:",
        workloadDefault,
      )) ?? workloadDefault;

      const workloadDir = path.resolve(ctx.cwd, workloadPath);

      // Validate workload exists
      if (!fs.existsSync(workloadDir)) {
        const cloneIt = await ctx.ui.confirm(
          "Workload not found",
          `${workloadPath} does not exist. Clone from a git URL?`,
        );
        if (cloneIt) {
          const gitUrl = await ctx.ui.input("Git URL to clone:", "");
          if (gitUrl) {
            ctx.ui.notify(`Cloning ${gitUrl} into ${workloadPath}...`, "info");
            try {
              execSync(`git clone --depth 1 ${gitUrl} ${workloadPath}`, {
                encoding: "utf-8",
                stdio: ["pipe", "pipe", "pipe"],
              });
              ctx.ui.notify("Clone complete.", "success");
            } catch (err: any) {
              ctx.ui.notify(`Clone failed: ${err.message}`, "error");
              return;
            }
          } else {
            ctx.ui.notify("Charm init cancelled — no workload source.", "info");
            return;
          }
        } else {
          ctx.ui.notify("Charm init cancelled. Clone the workload first.", "info");
          return;
        }
      }

      // Check if target charm dir exists and isn't empty
      if (fs.existsSync(charmDir) && !isDirEmpty(charmDir)) {
        const proceed = await ctx.ui.confirm(
          "Directory not empty",
          `${charmSubdir} already has files. Write only new files (charmcraft.yaml & src/charm.py will still be updated)?`,
        );
        if (!proceed) {
          ctx.ui.notify("Charm init cancelled.", "info");
          return;
        }
      }

      // Scaffold skeleton + research + fill
      ctx.ui.notify("Scaffolding skeleton charm files...", "info");
      fs.mkdirSync(charmDir, { recursive: true });

      let created: string[] = [];
      let skipped: string[] = [];
      const existingYaml = path.join(charmDir, "charmcraft.yaml");
      if (!fs.existsSync(existingYaml)) {
        const result = scaffoldCharm(charmName, charmDir, true);
        created = result.created;
        skipped = result.skipped;
      }

      ctx.ui.notify("Researching workload...", "info");
      const analysis = analyseWorkload(workloadDir, charmName);

      ctx.ui.notify("Writing filled charmcraft.yaml and src/charm.py...", "info");
      const ctxTmpl = makeContext(charmName);
      const files = filledFiles(ctxTmpl, analysis);
      let written = 0;
      for (const [relPath, content] of files) {
        const fullPath = path.join(charmDir, relPath);
        if (relPath === "charmcraft.yaml" || relPath === "src/charm.py") {
          writeFile(fullPath, content);
          written++;
        } else if (!fs.existsSync(fullPath)) {
          writeFile(fullPath, content);
          written++;
        }
      }

      const lines: string[] = [];
      lines.push(`Charm "${charmName}" initialized in ${charmSubdir}`);
      lines.push(`"""`);
      lines.push(`Detected: ${analysis.language}${analysis.framework !== "none" ? " (" + analysis.framework + ")" : ""}`);
      lines.push(`Command: ${analysis.command}`);
      if (analysis.port) lines.push(`Port: ${analysis.port}`);
      if (written > 0) lines.push(`Wrote ${written} files`);

      ctx.ui.notify(lines.join("\n"), "success");
    },
  });

  // ── dashcraft tool ────────────────────────────────────────────────────

  pi.registerTool({
    name: "dashcraft",
    label: "dashcraft",
    description:
      "Initialize a Juju charm project from a cloned workload — charming, but fast. " +
      "Researches the workload and writes charmcraft.yaml and src/charm.py. " +
      "By default this tool REFUSES to overwrite existing charmcraft.yaml or " +
      "src/charm.py — pass force=true to overwrite. " +
      "Note: when run via `dashcraft pack`, the CLI already pre-fills these " +
      "files server-side, so this tool is usually unnecessary in the AI loop.",
    promptSnippet: "dashcraft: scaffold a Juju charm from a cloned workload source (only if files aren't already filled)",
    promptGuidelines: [
      "Use dashcraft ONLY when the charm directory has no charmcraft.yaml yet (interactive scaffolding flow).",
      "When invoked from `dashcraft pack`, do NOT call this tool — the CLI has already filled charmcraft.yaml and src/charm.py from a deterministic analysis. Calling dashcraft would either be a no-op or require force=true.",
      "dashcraft needs two arguments: directory (charm project root) and workload (cloned upstream source). Both are required.",
      "If the workload isn't cloned yet, use git clone first.",
      "After scaffolding (or skipping), run charm_lint and charm_test_unit. Only consult /skill:relations, /skill:operational-patterns etc. once tests pass.",
    ],
    parameters: Type.Object({
      directory: Type.String({
        description:
          "Path to the charm project directory. Must contain (or will be created with) a charmcraft.yaml. " +
          "The tool writes charmcraft.yaml and src/charm.py based on workload analysis.",
      }),
      workload: Type.String({
        description:
          "Path to a cloned workload source directory on disk. " +
          "The tool reads this directory to detect the language, framework, startup command, ports, and configuration. " +
          "Clone with: git clone <url> /tmp/workload",
      }),
      force: Type.Optional(
        Type.Boolean({
          description:
            "Overwrite an existing charmcraft.yaml or src/charm.py. Defaults to false; " +
            "without it the tool refuses to clobber pre-filled files.",
        }),
      ),
    }),
    async execute(_toolCallId, params, signal, onUpdate, ctx) {
      const charmDir = path.resolve(ctx.cwd, params.directory.trim());
      const workloadDir = path.resolve(ctx.cwd, params.workload.trim());

      // Validate workload directory
      if (!fs.existsSync(workloadDir)) {
        return {
          content: [{ type: "text", text: `Error: Workload directory "${params.workload}" does not exist. Clone the upstream source first.` }],
          details: { error: "workload_not_found", workload: params.workload },
        };
      }
      if (!fs.statSync(workloadDir).isDirectory()) {
        return {
          content: [{ type: "text", text: `Error: "${params.workload}" is not a directory.` }],
          details: { error: "workload_not_dir", workload: params.workload },
        };
      }

      // Determine charm name from directory
      let charmName = path.basename(charmDir);
      const existingYaml = path.join(charmDir, "charmcraft.yaml");
      if (fs.existsSync(existingYaml)) {
        // Try to read existing name
        const existing = tryRead(existingYaml);
        const nameMatch = existing.match(/^name:\s*(\S+)/m);
        if (nameMatch && nameMatch[1] !== "TODO" && !nameMatch[1].startsWith("TODO")) {
          charmName = nameMatch[1];
        }
      }
      if (!/^[a-z][a-z0-9-]*$/.test(charmName)) {
        return {
          content: [{ type: "text", text: `Error: Could not determine a valid charm name from "${charmDir}". Ensure the directory name is kebab-case.` }],
          details: { error: "invalid_charm_name", dir: charmDir },
        };
      }

      // Refuse to clobber pre-filled files unless force=true.
      const existingCharmPy = path.join(charmDir, "src", "charm.py");
      const yamlPresent = fs.existsSync(existingYaml);
      const charmPyPresent = fs.existsSync(existingCharmPy);
      const force = params.force === true;
      if ((yamlPresent || charmPyPresent) && !force) {
        const present: string[] = [];
        if (yamlPresent) present.push("charmcraft.yaml");
        if (charmPyPresent) present.push("src/charm.py");
        return {
          content: [{
            type: "text",
            text:
              `${present.join(" and ")} already exist in ${params.directory}. ` +
              "Skipping. If you really want to regenerate from workload analysis, " +
              "call dashcraft again with force=true.\n\n" +
              "Otherwise, proceed with charm_lint and charm_test_unit on the existing files.",
          }],
          details: { skipped: present, directory: params.directory, force: false },
        };
      }

      onUpdate?.({ content: [{ type: "text", text: "Checking charm directory..." }] });
      fs.mkdirSync(charmDir, { recursive: true });

      let created: string[] = [];
      let skipped: string[] = [];
      if (!yamlPresent) {
        // Charm directory is empty — scaffold skeleton first
        onUpdate?.({ content: [{ type: "text", text: "Scaffolding skeleton charm files..." }] });
        const result = scaffoldCharm(charmName, charmDir, true);
        created = result.created;
        skipped = result.skipped;
      }

      onUpdate?.({ content: [{ type: "text", text: "Researching workload (reading source files, Dockerfiles, configs)..." }] });
      if (signal?.aborted) return { content: [{ type: "text", text: "Cancelled." }], details: {} };

      const analysis = analyseWorkload(workloadDir, charmName);

      onUpdate?.({ content: [{ type: "text", text: "Writing charmcraft.yaml and src/charm.py from analysis..." }] });

      const ctxTmpl = makeContext(charmName);
      const files = filledFiles(ctxTmpl, analysis);
      let written = 0;
      for (const [relPath, content] of files) {
        const fullPath = path.join(charmDir, relPath);
        if (relPath === "charmcraft.yaml" || relPath === "src/charm.py") {
          writeFile(fullPath, content);
          written++;
        } else if (!fs.existsSync(fullPath)) {
          writeFile(fullPath, content);
          written++;
        }
      }

      let msg = `Charm "${charmName}" initialized from workload analysis.\n\n`;
      msg += `**Detected:**\n`;
      msg += `- Name: ${analysis.name}\n`;
      msg += `- Language: ${analysis.language}${analysis.framework !== "none" ? " (" + analysis.framework + ")" : ""}\n`;
      msg += `- Command: \`${analysis.command}\`\n`;
      if (analysis.port) msg += `- Port: ${analysis.port}\n`;
      if (analysis.hasDockerfile) msg += `- Dockerfile: yes (${analysis.dockerExposePorts.length > 0 ? "exposes " + analysis.dockerExposePorts.join(", ") : "no EXPOSE"})\n`;
      if (Object.keys(analysis.envVars).length > 0) {
        msg += `- Env vars detected: ${Object.keys(analysis.envVars).join(", ")}\n`;
      }
      msg += `\n**Files written:** ${written} (including charmcraft.yaml, src/charm.py)\n`;
      // Order matches the agent's one-shot prompt: validate first, then
      // consult skills only if a deeper feature (relations, observability,
      // etc.) needs to be added.
      msg += `\n**Next steps (in order):**\n`;
      msg += `1. Review \`charmcraft.yaml\` and \`src/charm.py\` in \`${params.directory}\`\n`;
      msg += `2. Run \`charm_lint\` and fix any failures\n`;
      msg += `3. Run \`charm_test_unit\` and fix any failures\n`;
      msg += `4. If the workload needs deeper relation/observability work, load /skill:relations, /skill:operational-patterns or /skill:observability and apply patterns\n`;
      msg += `5. Re-run \`charm_lint\` and \`charm_test_unit\` to confirm\n`;
      msg += `6. Run \`charm_build\` to pack the charm\n`;

      return {
        content: [{ type: "text", text: msg }],
        details: { charmName, directory: params.directory, workload: params.workload, analysis, created, skipped, written, force },
      };
    },

    renderCall(args, theme, _context) {
      let text = theme.fg("toolTitle", theme.bold("dashcraft"));
      if (args.directory) text += " " + theme.fg("muted", args.directory);
      if (args.workload) text += " " + theme.fg("dim", "← " + args.workload);
      return new Text(text, 0, 0);
    },

    renderResult(result, _options, theme, _context) {
      const details = result.details as { error?: string; analysis?: WorkloadAnalysis; charmName?: string } | undefined;
      if (details?.error) {
        return new Text(theme.fg("error", `Error: ${details.error}`), 0, 0);
      }
      if (details?.analysis) {
        const a = details.analysis;
        return new Text(
          theme.fg("success", `✓ dashcraft "${details.charmName ?? "?"}"`) +
            " · " + theme.fg("muted", `${a.language}${a.framework !== "none" ? "/" + a.framework : ""}`) +
            " · " + theme.fg("dim", `cmd: ${a.command.split(" ")[0]}`),
          0,
          0,
        );
      }
      const text = result.content[0];
      return new Text(text?.type === "text" ? "Done" : "Done", 0, 0);
    },
  });

  // ── charm_build tool ───────────────────────────────────────────────────

  pi.registerTool({
    name: "charm_build",
    label: "Charm Build",
    description:
      "Build a Juju charm using `quickpack` (a prereq installation tool that also packs). Runs in the project root directory.",
    promptSnippet: "Build a Juju charm with quickpack",
    promptGuidelines: [
      "Use charm_build when the user asks to build or pack a charm. Run it from the charm project root.",
    ],
    parameters: Type.Object({
      directory: Type.Optional(
        Type.String({
          description: "Charm project directory. Defaults to current directory.",
        }),
      ),
    }),
    async execute(_toolCallId, params, signal, onUpdate, ctx) {
      const cwd = params.directory || ".";
      const absDir = path.resolve(ctx.cwd, cwd);

      if (!fs.existsSync(path.join(absDir, "charmcraft.yaml"))) {
        return {
          content: [
            {
              type: "text",
              text: `Error: No charmcraft.yaml found in "${cwd}". Are you in a charm project directory?`,
            },
          ],
          details: { error: "not_a_charm_project", directory: cwd },
        };
      }

      onUpdate?.({ content: [{ type: "text", text: "Installing prereqs & building charm..." }] });

      if (!quickpackAvailable()) {
        return {
          content: [{
            type: "text",
            text: "Error: quickpack is not installed. Install it with: `uv tool install juju-cantrip`",
          }],
          details: { error: "quickpack_missing" },
        };
      }

      try {
        const result = await runQuickpack(["pack"], absDir, {
          timeoutMs: 300_000, // 5 min
          signal,
          onLine: (line) => onUpdate?.({ content: [{ type: "text", text: line }] }),
        });

        if (!result.ok) {
          return {
            content: [{ type: "text", text: `Charm build failed:\n${result.output}` }],
            details: { error: "build_failed", output: result.output },
            isError: true,
          };
        }

        return {
          content: [{ type: "text", text: `Charm built successfully:\n${result.output}` }],
          details: { output: result.output, directory: absDir },
        };
      } catch (err: any) {
        const stderr = err.stderr || err.message || String(err);
        return {
          content: [
            {
              type: "text",
              text: `Charm build failed:\n${stderr}`,
            },
          ],
          details: { error: "build_failed", stderr },
          isError: true,
        };
      }
    },

    renderCall(args, theme, _context) {
      let text = theme.fg("toolTitle", theme.bold("charm_build"));
      if (args.directory) text += " " + theme.fg("dim", args.directory);
      return new Text(text, 0, 0);
    },

    renderResult(result, _options, theme, _context) {
      const details = result.details as { error?: string } | undefined;
      if (details?.error) {
        return new Text(theme.fg("error", `Build failed: ${details.error}`), 0, 0);
      }
      return new Text(theme.fg("success", "✓ Charm built successfully"), 0, 0);
    },
  });

  // ── charm_lint tool ────────────────────────────────────────────────────

  pi.registerTool({
    name: "charm_lint",
    label: "Charm Lint",
    description:
      "Lint a Juju charm project via `uv run --group lint`. Runs ruff check, " +
      "ruff format --check, codespell, and pyright sequentially; stops at " +
      "the first failure. Bypasses tox to avoid a 30–90s per-env venv build " +
      "on first call.",
    promptSnippet: "Lint a Juju charm project (ruff, codespell, pyright via uv)",
    promptGuidelines: [
      "Use charm_lint to check a charm's code quality. Run from the charm project root.",
      "On failure the transcript shows the first failed check; fix that one and re-run.",
    ],
    parameters: Type.Object({
      directory: Type.Optional(
        Type.String({
          description: "Charm project directory. Defaults to current directory.",
        }),
      ),
    }),
    async execute(_toolCallId, params, signal, onUpdate, ctx) {
      const cwd = params.directory || ".";
      const absDir = path.resolve(ctx.cwd, cwd);

      onUpdate?.({ content: [{ type: "text", text: "Linting charm..." }] });

      const checks: Array<{ name: string; args: string[] }> = [
        { name: "ruff check", args: ["run", "--group", "lint", "ruff", "check", "src", "tests"] },
        { name: "ruff format", args: ["run", "--group", "lint", "ruff", "format", "--check", "--diff", "src", "tests"] },
        { name: "codespell", args: ["run", "--group", "lint", "codespell", "."] },
        { name: "pyright", args: ["run", "--group", "lint", "pyright"] },
      ];

      const transcript: string[] = [];
      for (const { name, args } of checks) {
        if (signal?.aborted) {
          return { content: [{ type: "text", text: "Cancelled." }], details: { error: "cancelled" } };
        }
        const result = await runUv(args, absDir, 120_000, signal, (line) => {
          onUpdate?.({ content: [{ type: "text", text: `${name}: ${line}` }] });
        });
        transcript.push(`--- ${name} ---\n${result.output || "(no output)"}`);
        if (!result.ok) {
          return {
            content: [{
              type: "text",
              text: `Lint failed at ${name}:\n\n${transcript.join("\n\n")}`,
            }],
            details: { error: "lint_failed", failed_check: name, transcript: transcript.join("\n\n") },
            isError: true,
          };
        }
      }

      return {
        content: [{
          type: "text",
          text: `Lint passed (${checks.length} checks).\n\n${transcript.join("\n\n")}`,
        }],
        details: { transcript: transcript.join("\n\n") },
      };
    },

    renderResult(result, _options, theme, _context) {
      const details = result.details as { error?: string; failed_check?: string } | undefined;
      if (details?.error) {
        const tail = details.failed_check ? ` (${details.failed_check})` : "";
        return new Text(theme.fg("warning", `⚠ Lint failed${tail}`), 0, 0);
      }
      return new Text(theme.fg("success", "✓ Lint passed"), 0, 0);
    },
  });

  // ── charm_test_unit tool ───────────────────────────────────────────────

  pi.registerTool({
    name: "charm_test_unit",
    label: "Charm Unit Test",
    description:
      "Run unit tests for a Juju charm via `uv run --group unit pytest`. " +
      "Bypasses tox to avoid a 30–90s per-env venv build on first call. " +
      "Coverage instrumentation is skipped here; use tox locally if needed.",
    promptSnippet: "Run unit tests for a Juju charm (pytest via uv)",
    promptGuidelines: [
      "Use charm_test_unit to run a charm's unit tests. Run from the charm project root.",
    ],
    parameters: Type.Object({
      directory: Type.Optional(
        Type.String({
          description: "Charm project directory. Defaults to current directory.",
        }),
      ),
    }),
    async execute(_toolCallId, params, signal, onUpdate, ctx) {
      const cwd = params.directory || ".";
      const absDir = path.resolve(ctx.cwd, cwd);

      onUpdate?.({ content: [{ type: "text", text: "Running unit tests..." }] });

      const result = await runUv(
        ["run", "--group", "unit", "pytest", "tests/unit", "-v", "--tb=native"],
        absDir,
        120_000,
        signal,
        (line) => onUpdate?.({ content: [{ type: "text", text: line }] }),
      );

      if (!result.ok) {
        return {
          content: [{ type: "text", text: `Unit tests failed:\n${result.output}` }],
          details: { error: "tests_failed", output: result.output },
          isError: true,
        };
      }

      return {
        content: [{ type: "text", text: `Unit tests passed:\n${result.output}` }],
        details: { output: result.output },
      };
    },

    renderResult(result, _options, theme, _context) {
      const details = result.details as { error?: string } | undefined;
      if (details?.error) {
        return new Text(theme.fg("error", "✗ Unit tests failed"), 0, 0);
      }
      return new Text(theme.fg("success", "✓ Unit tests passed"), 0, 0);
    },
  });

  // ── charm_test_integration tool ───────────────────────────────────────

  pi.registerTool({
    name: "charm_test_integration",
    label: "Charm Integration Test",
    description:
      "Run integration tests for a Juju charm via `uv run --group integration pytest`. " +
      "Requires a Juju controller and model. See /skill:charm-testing for test patterns.",
    promptSnippet: "Run integration tests for a Juju charm (pytest via uv; requires Juju controller)",
    promptGuidelines: [
      "Use charm_test_integration when the user asks to run integration tests. These require a live Juju controller. Read /skill:charm-testing first for the test framework.",
    ],
    parameters: Type.Object({
      directory: Type.Optional(
        Type.String({
          description: "Charm project directory. Defaults to current directory.",
        }),
      ),
    }),
    async execute(_toolCallId, params, signal, onUpdate, ctx) {
      const cwd = params.directory || ".";
      const absDir = path.resolve(ctx.cwd, cwd);

      onUpdate?.({ content: [{ type: "text", text: "Running integration tests..." }] });

      const result = await runUv(
        [
          "run", "--group", "integration",
          "pytest", "tests/integration", "-v", "--tb=native", "--log-cli-level=INFO",
        ],
        absDir,
        600_000,
        signal,
        (line) => onUpdate?.({ content: [{ type: "text", text: line }] }),
      );

      if (!result.ok) {
        return {
          content: [{ type: "text", text: `Integration tests failed:\n${result.output}` }],
          details: { error: "integration_failed", output: result.output },
          isError: true,
        };
      }

      return {
        content: [{ type: "text", text: `Integration tests passed:\n${result.output}` }],
        details: { output: result.output },
      };
    },

    renderResult(result, _options, theme, _context) {
      const details = result.details as { error?: string } | undefined;
      if (details?.error) {
        return new Text(theme.fg("error", "✗ Integration tests failed"), 0, 0);
      }
      return new Text(theme.fg("success", "✓ Integration tests passed"), 0, 0);
    },
  });

  // ── charm_help tool ───────────────────────────────────────────────────

  pi.registerTool({
    name: "charm_help",
    label: "Charm Help",
    description:
      "List available charm-building skills and point to reference docs. " +
      "Call this when the user asks 'how do I...' for charm development.",
    promptSnippet: "Show available charm skills and reference documentation",
    promptGuidelines: [
      "Use charm_help when the user asks general questions about Juju charm development or wants to know what tools/skills are available.",
      "After charm_help returns, use /skill:<name> to load a specific skill's full guidance into context.",
    ],
    parameters: Type.Object({}),
    async execute(_toolCallId, _params, _signal, _onUpdate, _ctx) {
      const skills = [
        ["quick-charm-workflow", "End-to-end workflow: detect framework, scaffold, build, test, deploy"],
        ["relations", "Designing and implementing relation data bags for charm integrations"],
        ["charm-testing", "Unit tests with ops.testing (Scenario) and integration tests with Jubilant"],
        ["observability", "Adding COS observability (metrics, logs, dashboards, tracing)"],
        ["operational-patterns", "Actions, config validation, status, backup/restore, secrets"],
        ["quality-review", "Security review and bug-hunting for charm code"],
        ["debugging", "Systematic diagnosis, debug iteration, and jhack tooling"],
      ];

      let msg = "# Juju Charm Development Skills\n\n";
      msg += "Load any skill with `/skill:<name>` to get full guidance.\n\n";
      msg += "| Skill | Purpose |\n|-------|--------|\n";
      for (const [name, desc] of skills) {
        msg += `| \`${name}\` | ${desc} |\n`;
      }
      msg += "\n## Workflow Quick Reference\n\n";
      msg += "1. **Start**: `/skill:quick-charm-workflow` — determine charm path, scaffold\n";
      msg += "2. **Implement**: `/skill:relations`, `/skill:operational-patterns`, `/skill:observability`\n";
      msg += "3. **Test**: `/skill:charm-testing` — Scenario unit tests + Jubilant integration tests\n";
      msg += "4. **Review**: `/skill:quality-review` — security audit, bug hunt\n";
      msg += "5. **Debug**: `/skill:debugging` — diagnose and fix issues\n";
      msg += "\n## Tools Available\n\n";
      msg += "- `dashcraft` — initialize a charm: takes (directory, workload), researches workload, writes charmcraft.yaml & src/charm.py\n";
      msg += "- `charm_build` — run `quickpack pack` (installs prereqs, then packs)\n";
      msg += "- `charm_lint` — ruff/codespell/pyright via `uv run --group lint`\n";
      msg += "- `charm_test_unit` — pytest via `uv run --group unit`\n";
      msg += "- `charm_test_integration` — pytest via `uv run --group integration`\n";

      return {
        content: [{ type: "text", text: msg }],
        details: {},
      };
    },

    renderCall(_args, theme, _context) {
      return new Text(
        theme.fg("toolTitle", theme.bold("charm_help")),
        0,
        0,
      );
    },

    renderResult(result, _options, _theme, _context) {
      const text = result.content[0];
      return new Text(text?.type === "text" ? "Charm skills listed" : "Done", 0, 0);
    },
  });

  // ── Session start ──────────────────────────────────────────────────────

  pi.on("session_start", async (_event, ctx) => {
    ctx.ui.setWidget(
      "dashcraft",
      [
        "  🪄 dashcraft — charming, but fast",
        "  /dashcraft · dashcraft(dir, workload) · charm_build · charm_lint · charm_test",
        "  /skill:quick-charm-workflow · relations · charm-testing · observability · operational-patterns · quality-review · debugging",
      ],
    );
  });
}
