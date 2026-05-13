/**
 * Juju Charm Extension for pi
 *
 * Provides tools and commands for building Juju charms. Starts with a basic
 * scaffold matching `charmcraft init --profile kubernetes`.
 *
 * Features:
 *   /charm-init [name]  — scaffold a new charm interactively
 *   charm_init          — tool for the LLM to scaffold charms
 *   charm_build         — run `charmcraft pack`
 *   charm_lint          — run `tox run -e lint`
 *   charm_test_unit     — run `tox run -e unit`
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Text } from "@earendil-works/pi-tui";
import { Type } from "typebox";
import * as fs from "node:fs";
import * as path from "node:path";
import { execSync } from "node:child_process";

import { allFiles, makeContext } from "./templates";

// ── Helpers ─────────────────────────────────────────────────────────────────

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
function scaffoldCharm(charmName: string, targetDir: string): {
  created: string[];
  skipped: string[];
} {
  const ctx = makeContext(charmName);
  const files = allFiles(ctx);
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

// ── Extension ───────────────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  // ── /charm-init command ─────────────────────────────────────────────────

  pi.registerCommand("charm-init", {
    description: "Scaffold a new Juju charm from the standard template",
    async handler(args, ctx) {
      if (!ctx.hasUI) {
        ctx.ui.notify("/charm-init requires interactive mode", "error");
        return;
      }

      let charmName = args?.trim() || "";

      // Prompt for name if not provided
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

      // Prompt for target directory
      const subdir = (await ctx.ui.input(
        "Target directory (relative):",
        `./${charmName}`,
      )) ?? `./${charmName}`;

      const targetDir = path.resolve(ctx.cwd, subdir);

      // Check if target exists and isn't empty
      if (fs.existsSync(targetDir) && !isDirEmpty(targetDir)) {
        const proceed = await ctx.ui.confirm(
          "Directory not empty",
          `${subdir} already has files. Skip existing and write only new files?`,
        );
        if (!proceed) {
          ctx.ui.notify("Charm init cancelled.", "info");
          return;
        }
      }

      fs.mkdirSync(targetDir, { recursive: true });
      const { created, skipped } = scaffoldCharm(charmName, targetDir);

      const lines: string[] = [];
      if (created.length > 0) {
        lines.push(`Created ${created.length} files:`);
        for (const f of created) lines.push(`  ✓ ${f}`);
      }
      if (skipped.length > 0) {
        lines.push(`Skipped ${skipped.length} existing files:`);
        for (const f of skipped) lines.push(`  - ${f}`);
      }

      ctx.ui.notify(
        `Charm "${charmName}" scaffolded in ${subdir}\n${lines.join("\n")}`,
        "success",
      );
    },
  });

  // ── charm_init tool ────────────────────────────────────────────────────

  pi.registerTool({
    name: "charm_init",
    label: "Charm Init",
    description:
      "Scaffold a new Juju charm project from the standard kubernetes template. " +
      "Creates all needed files: charmcraft.yaml, src/charm.py, pyproject.toml, " +
      "tests, tox.ini, etc.",
    promptSnippet: "Initialize a new Juju charm project from a template",
    promptGuidelines: [
      "Use charm_init when the user asks to create a new Juju charm, initialize a charm project, or scaffold a charm.",
      "After charm_init creates the files, review charmcraft.yaml and src/charm.py with the user to customize them.",
    ],
    parameters: Type.Object({
      name: Type.String({
        description:
          "Charm name in kebab-case (e.g. 'my-app'). Used for the package name, class name, and module name.",
      }),
      directory: Type.Optional(
        Type.String({
          description:
            "Target directory relative to current working directory. Defaults to './<name>'.",
        }),
      ),
      force: Type.Optional(
        Type.Boolean({
          description:
            "If true, proceed even if target directory already has files. Existing files are never overwritten.",
          default: false,
        }),
      ),
    }),
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const charmName = params.name.trim();
      if (!/^[a-z][a-z0-9-]*$/.test(charmName)) {
        return {
          content: [
            {
              type: "text",
              text: `Error: Invalid charm name "${charmName}". Must be kebab-case (e.g. "my-app").`,
            },
          ],
          details: { error: "invalid_name", name: charmName },
        };
      }

      const subdir = params.directory?.trim() || `./${charmName}`;
      const targetDir = path.resolve(process.cwd(), subdir);

      if (fs.existsSync(targetDir) && !isDirEmpty(targetDir) && !params.force) {
        return {
          content: [
            {
              type: "text",
              text: `Error: Directory "${subdir}" already contains files. Use force=true to skip existing files, or choose a different directory.`,
            },
          ],
          details: { error: "dir_not_empty", directory: subdir },
        };
      }

      fs.mkdirSync(targetDir, { recursive: true });
      const { created, skipped } = scaffoldCharm(charmName, targetDir);

      let msg = `Charm "${charmName}" scaffolded in ${subdir}.\n`;
      if (created.length > 0) {
        msg += `\nCreated ${created.length} files:\n`;
        for (const f of created) msg += `  ✓ ${f}\n`;
      }
      if (skipped.length > 0) {
        msg += `\nSkipped ${skipped.length} existing files:\n`;
        for (const f of skipped) msg += `  - ${f}\n`;
      }
      msg +=
        "\nNext: review charmcraft.yaml and src/charm.py, then run `charmcraft pack` to build.";

      return {
        content: [{ type: "text", text: msg }],
        details: {
          charmName,
          directory: subdir,
          created,
          skipped,
        },
      };
    },

    renderCall(args, theme, _context) {
      return new Text(
        theme.fg("toolTitle", theme.bold("charm_init ")) +
          theme.fg("muted", args.name ?? ""),
        0,
        0,
      );
    },

    renderResult(result, _options, theme, _context) {
      const details = result.details as { error?: string; created?: string[]; charmName?: string } | undefined;
      if (details?.error) {
        return new Text(theme.fg("error", `Error: ${details.error}`), 0, 0);
      }
      if (details?.created) {
        return new Text(
          theme.fg("success", `✓ Initialized "${details.charmName ?? "?"}" - ${details.created.length} files created`),
          0,
          0,
        );
      }
      const text = result.content[0];
      return new Text(text?.type === "text" ? text.text : "Done", 0, 0);
    },
  });

  // ── charm_build tool ───────────────────────────────────────────────────

  pi.registerTool({
    name: "charm_build",
    label: "Charm Build",
    description:
      "Build a Juju charm using `charmcraft pack`. Runs in the project root directory.",
    promptSnippet: "Build a Juju charm with charmcraft pack",
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

      onUpdate?.({ content: [{ type: "text", text: "Building charm..." }] });

      try {
        // Check if charmcraft is available
        try {
          execSync("which charmcraft", { encoding: "utf-8" });
        } catch {
          return {
            content: [
              {
                type: "text",
                text: "Error: charmcraft is not installed. Install it with: `sudo snap install charmcraft --classic`",
              },
            ],
            details: { error: "charmcraft_missing" },
          };
        }

        const output = execSync("charmcraft pack", {
          cwd: absDir,
          encoding: "utf-8",
          timeout: 300_000, // 5 min
          signal,
          stdio: ["pipe", "pipe", "pipe"],
        });

        return {
          content: [
            {
              type: "text",
              text: `Charm built successfully:\n${output.trim()}`,
            },
          ],
          details: { output: output.trim(), directory: absDir },
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
      "Lint a Juju charm project using `tox run -e lint`. Checks code style with ruff, codespell, and pyright.",
    promptSnippet: "Lint a Juju charm project (ruff, codespell, pyright)",
    promptGuidelines: [
      "Use charm_lint when the user asks to lint or check a charm's code quality. Run from the charm project root.",
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

      try {
        const output = execSync("tox run -e lint", {
          cwd: absDir,
          encoding: "utf-8",
          timeout: 120_000,
          signal,
          stdio: ["pipe", "pipe", "pipe"],
        });

        return {
          content: [
            {
              type: "text",
              text: `Lint passed:\n${output.trim()}`,
            },
          ],
          details: { output: output.trim() },
        };
      } catch (err: any) {
        const stderr = err.stderr || err.message || String(err);
        return {
          content: [
            {
              type: "text",
              text: `Lint failed:\n${stderr}`,
            },
          ],
          details: { error: "lint_failed", stderr },
          isError: true,
        };
      }
    },

    renderResult(result, _options, theme, _context) {
      const details = result.details as { error?: string } | undefined;
      if (details?.error) {
        return new Text(theme.fg("warning", "⚠ Lint issues found"), 0, 0);
      }
      return new Text(theme.fg("success", "✓ Lint passed"), 0, 0);
    },
  });

  // ── charm_test_unit tool ───────────────────────────────────────────────

  pi.registerTool({
    name: "charm_test_unit",
    label: "Charm Unit Test",
    description:
      "Run unit tests for a Juju charm using `tox run -e unit`.",
    promptSnippet: "Run unit tests for a Juju charm",
    promptGuidelines: [
      "Use charm_test_unit when the user asks to run charm unit tests. Run from the charm project root.",
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

      try {
        const output = execSync("tox run -e unit", {
          cwd: absDir,
          encoding: "utf-8",
          timeout: 120_000,
          signal,
          stdio: ["pipe", "pipe", "pipe"],
        });

        return {
          content: [
            {
              type: "text",
              text: `Unit tests passed:\n${output.trim()}`,
            },
          ],
          details: { output: output.trim() },
        };
      } catch (err: any) {
        const stderr = err.stderr || err.message || String(err);
        return {
          content: [
            {
              type: "text",
              text: `Unit tests failed:\n${stderr}`,
            },
          ],
          details: { error: "tests_failed", stderr },
          isError: true,
        };
      }
    },

    renderResult(result, _options, theme, _context) {
      const details = result.details as { error?: string } | undefined;
      if (details?.error) {
        return new Text(theme.fg("error", "✗ Unit tests failed"), 0, 0);
      }
      return new Text(theme.fg("success", "✓ Unit tests passed"), 0, 0);
    },
  });

  // ── Session start ──────────────────────────────────────────────────────

  pi.on("session_start", async (_event, ctx) => {
    ctx.ui.setWidget(
      "juju-charm",
      [
        "  🪄 Juju Charm extension active",
        "  /charm-init [name] · charm_init · charm_build · charm_lint · charm_test_unit",
      ],
    );
  });
}