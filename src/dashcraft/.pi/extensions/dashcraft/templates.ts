/**
 * Juju Charm templates — mirroring `charmcraft init --profile kubernetes`.
 *
 * Two modes:
 *   1.  Skeleton — placeholder files where key fields need filling
 *   2.  Filled  — fully populated from workload research
 *
 * All templates use `{charm_name}` (kebab-case), `{class_name}` (PascalCase + Charm),
 * and `{module_name}` (snake_case) for interpolation.
 */

/** Convert kebab-case name to PascalCase + "Charm" suffix. */
export function toClassName(charmName: string): string {
  return (
    charmName
      .split("-")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join("") + "Charm"
  );
}

/** Convert kebab-case name to snake_case (module name). */
export function toModuleName(charmName: string): string {
  return charmName.replace(/-/g, "_");
}

/** Convert kebab-case to Title Case for display. */
export function toTitle(charmName: string): string {
  return charmName
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

// ── Template helpers ────────────────────────────────────────────────────────

export interface CharmTemplateContext {
  charmName: string;    // kebab-case, e.g. "my-app"
  className: string;    // PascalCase + Charm, e.g. "MyAppCharm"
  moduleName: string;   // snake_case, e.g. "my_app"
  title: string;        // Title Case, e.g. "My App"
}

/** Results from workload analysis used to fill templates. */
export interface WorkloadAnalysis {
  name: string;               // detected workload name
  summary: string;            // one-line summary (from README or detected)
  description: string;        // multi-paragraph description
  language: string;           // "python" | "go" | "nodejs" | "rust" | "unknown"
  framework: string;          // "flask" | "django" | "fastapi" | "express" | "spring" | "none"
  command: string;            // startup command, e.g. "/usr/bin/my-app" or "python -m flask run"
  port: number;               // primary HTTP port
  envVars: Record<string, string>; // env vars with default values
  hasDockerfile: boolean;
  hasDockerCompose: boolean;
  dockerExposePorts: number[];
  dockerCmdHint: string;      // CMD / ENTRYPOINT from Dockerfile if found
  needsDatabase: boolean;
  needsCache: boolean;
  isWebApp: boolean;
  extraPackages: string[];    // apt/system packages needed at runtime
  hasHealthEndpoint: boolean;  // has a /health or /healthz endpoint
  healthEndpoint: string;      // URL path to health endpoint, e.g. "/health"
  hasK8sManifests: boolean;    // has Kubernetes deployment/service manifests
  needsStorage: boolean;       // requires persistent storage
  needsClustering: boolean;    // requires peer clustering / HA
  hasRedis: boolean;           // specifically depends on Redis
  hasPostgres: boolean;        // specifically depends on PostgreSQL
  hasMySQL: boolean;           // specifically depends on MySQL
}

export function makeContext(charmName: string): CharmTemplateContext {
  return {
    charmName,
    className: toClassName(charmName),
    moduleName: toModuleName(charmName),
    title: toTitle(charmName),
  };
}

/** Default empty analysis to signal we haven't researched yet. */
export function emptyAnalysis(name: string): WorkloadAnalysis {
  return {
    name,
    summary: "",
    description: "",
    language: "unknown",
    framework: "none",
    command: "/bin/foo  # TODO: set startup command",
    port: 8080,
    envVars: {},
    hasDockerfile: false,
    hasDockerCompose: false,
    dockerExposePorts: [],
    dockerCmdHint: "",
    needsDatabase: false,
    needsCache: false,
    isWebApp: false,
    extraPackages: [],
    hasHealthEndpoint: false,
    healthEndpoint: "",
    hasK8sManifests: false,
    needsStorage: false,
    needsClustering: false,
    hasRedis: false,
    hasPostgres: false,
    hasMySQL: false,
  };
}

// ── Skeleton templates (placeholders, key fields not filled) ────────────────

export function skeletonCharmcraftYaml(ctx: CharmTemplateContext): string {
  return [
    "# This file configures Charmcraft.",
    "# See https://documentation.ubuntu.com/charmcraft/stable/reference/files/charmcraft-yaml-file/",
    "type: charm",
    `name: ${ctx.charmName}`,
    `title: ${ctx.title} Charm`,
    "summary: TODO: A very short one-line summary of the charm.",
    "description: |",
    "  TODO: A single sentence that says what the charm is, concisely and memorably.",
    "",
    "  TODO: A paragraph of one to three short sentences, that describe what the charm does.",
    "",
    "  TODO: A third paragraph that explains what need the charm meets.",
    "",
    "  TODO: Finally, a paragraph that describes whom the charm is useful for.",
    "",
    "# Documentation:",
    "# https://documentation.ubuntu.com/charmcraft/stable/howto/build-guides/select-platforms/",
    "base: ubuntu@22.04  # TODO: confirm base",
    "platforms:",
    "  amd64:",
    "  arm64:",
    "",
    "parts:",
    "  charm:",
    "    plugin: uv",
    "    source: .",
    "    build-snaps:",
    "      - astral-uv",
    "",
    "# TODO: fill in config options based on workload",
    "config:",
    "  options:",
    "    log-level:",
    "      description: |",
    '        Configures the log level of the workload.',
    "",
    '        Acceptable values are: "info", "debug", "warning", "error" and "critical"',
    '      default: "info"',
    "      type: string",
    "",
    "# TODO: set container and resource names based on workload",
    "containers:",
    "  workload:",
    "    resource: workload-image",
    "",
    "resources:",
    "  workload-image:",
    "    type: oci-image",
    "    description: OCI image for the workload container",
    "    upstream-source: TODO: workload-image:tag",
    "",
  ].join("\n");
}

/** Generate a filled charmcraft.yaml from workload analysis. */
export function filledCharmcraftYaml(ctx: CharmTemplateContext, analysis: WorkloadAnalysis): string {
  const parts: string[] = [];
  parts.push("# This file configures Charmcraft.");
  parts.push("# See https://documentation.ubuntu.com/charmcraft/stable/reference/files/charmcraft-yaml-file/");
  parts.push("type: charm");
  parts.push(`name: ${ctx.charmName}`);
  parts.push(`title: ${ctx.title} Charm`);
  parts.push(`summary: ${analysis.summary || "Charm for " + ctx.title}`);
  parts.push("description: |");
  for (const line of (analysis.description || `A Juju charm for deploying and operating ${ctx.title}.`).split("\n")) {
    parts.push(`  ${line}`);
  }
  parts.push("");
  parts.push("base: ubuntu@24.04");
  parts.push("platforms:");
  parts.push("  amd64:");
  parts.push("  arm64:");
  parts.push("");

  parts.push("assumes:");
  parts.push("  - juju >= 3.6");
  parts.push("  - k8s-api");
  parts.push("");

  parts.push("parts:");
  parts.push("  charm:");
  parts.push("    plugin: uv");
  parts.push("    source: .");
  parts.push("    build-snaps:");
  parts.push("      - astral-uv");
  parts.push("");

  // ── Config ────────────────────────────────────────────────────
  parts.push("config:");
  parts.push("  options:");
  parts.push("    log-level:");
  parts.push("      description: |");
  parts.push('        Configures the log level of the workload.');
  parts.push('        Acceptable values are: "debug", "info", "warning", "error" and "critical"');
  parts.push('      default: "info"');
  parts.push("      type: string");
  if (analysis.port && analysis.port !== 8080) {
    parts.push("    port:");
    parts.push("      description: The port the workload listens on.");
    parts.push(`      default: ${analysis.port}`);
    parts.push("      type: int");
  }
  // Env vars as config options (skip infra keys handled by relations)
  for (const [key, val] of Object.entries(analysis.envVars)) {
    const configKey = key.toLowerCase().replace(/_/g, "-");
    const skipKeys = ["database-url", "db-url", "redis-url", "redis-host",
                       "postgres-url", "datasource-url", "mysql-url"];
    if (skipKeys.includes(configKey)) continue;
    parts.push(`    ${configKey}:`);
    parts.push(`      description: Sets the ${key} environment variable.`);
    parts.push(`      default: "${val}"`);
    parts.push("      type: string");
  }
  parts.push("");

  // ── Relations ─────────────────────────────────────────────────
  parts.push("provides:");
  parts.push("  metrics-endpoint:");
  parts.push("    interface: prometheus_scrape");
  parts.push("  grafana-dashboard:");
  parts.push("    interface: grafana_dashboard");
  if (analysis.isWebApp) {
    parts.push("  ingress:");
    parts.push("    interface: ingress");
  }
  if (analysis.needsDatabase || analysis.hasPostgres) {
    parts.push("  postgresql:");
    parts.push("    interface: postgresql_client");
  }
  parts.push("");

  parts.push("requires:");
  parts.push("  tracing:");
  parts.push("    interface: tracing");
  parts.push("    limit: 1");
  parts.push("    optional: true");
  parts.push("  logging:");
  parts.push("    interface: loki_push_api");
  parts.push("    optional: true");
  if (analysis.needsDatabase || analysis.hasPostgres) {
    parts.push("  database:");
    parts.push("    interface: postgresql_client");
    parts.push("    optional: true");
    parts.push("    limit: 1");
  }
  parts.push("");

  if (analysis.needsClustering) {
    parts.push("peers:");
    parts.push("  cluster:");
    parts.push("    interface: cluster");
    parts.push("");
  }

  // ── Storage ───────────────────────────────────────────────────
  if (analysis.needsStorage) {
    parts.push("storage:");
    parts.push("  data:");
    parts.push("    type: filesystem");
    parts.push("    location: /var/lib/app");
    parts.push("");
  }

  // ── Actions ───────────────────────────────────────────────────
  parts.push("actions:");
  parts.push("  health-check:");
  parts.push("    description: Run a comprehensive health check on the workload.");
  parts.push("  backup:");
  parts.push("    description: Create a backup of application data.");
  parts.push("    params:");
  parts.push("      path:");
  parts.push("        type: string");
  parts.push("        description: Destination path for the backup.");
  parts.push("        default: /var/backups");
  parts.push("  pause:");
  parts.push("    description: Pause the workload service.");
  parts.push("  resume:");
  parts.push("    description: Resume the workload service.");
  parts.push("  collect-diagnostics:");
  parts.push("    description: Collect diagnostic information about the deployment.");
  parts.push("");

  // ── Containers & Resources ────────────────────────────────────
  parts.push("containers:");
  parts.push("  workload:");
  parts.push("    resource: workload-image");
  parts.push("");
  parts.push("resources:");
  parts.push("  workload-image:");
  parts.push("    type: oci-image");
  parts.push("    description: OCI image for the workload container");
  parts.push(`    upstream-source: ${analysis.name}:latest  # TODO: confirm image tag`);
  parts.push("");

  return parts.join("\n");
}

/** Generate a skeleton src/charm.py with placeholders. */
export function skeletonSrcCharmPy(ctx: CharmTemplateContext): string {
  return [
    "#!/usr/bin/env python3",
    "# Copyright 2026 Ubuntu",
    "# See LICENSE file for licensing details.",
    "",
    '"""Charm the application."""',
    "",
    "import logging",
    "import time",
    "",
    "import ops",
    "",
    `import ${ctx.moduleName}`,
    "",
    "logger = logging.getLogger(__name__)",
    "",
    'SERVICE_NAME = "workload"',
    'CHECK_NAME = "service-ready"',
    "",
    "",
    `class ${ctx.className}(ops.CharmBase):`,
    '    """Charm the application."""',
    "",
    "    def __init__(self, framework: ops.Framework):",
    "        super().__init__(framework)",
    '        framework.observe(self.on["workload"].pebble_ready, self._on_pebble_ready)',
    '        self.container = self.unit.get_container("workload")',
    "",
    "    def _on_pebble_ready(self, event: ops.PebbleReadyEvent):",
    '        """Handle pebble-ready event."""',
    '        self.unit.status = ops.MaintenanceStatus("starting workload")',
    "        layer: ops.pebble.LayerDict = {",
    '            "services": {',
    "                SERVICE_NAME: {",
    '                    "override": "replace",',
    '                    "summary": "TODO: describe the workload service",',
    '                    "command": "/bin/foo  # TODO: change to the actual startup command",',
    '                    "startup": "enabled",',
    "                }",
    "            }",
    "        }",
    '        self.container.add_layer("workload", layer, combine=True)',
    "        self.container.replan()",
    "        self.wait_for_ready()",
    `        version = ${ctx.moduleName}.get_version()`,
    "        if version is not None:",
    "            self.unit.set_workload_version(version)",
    "        self.unit.status = ops.ActiveStatus()",
    "",
    "    def is_ready(self) -> bool:",
    '        """Check whether the workload is ready to use."""',
    "        for name, service_info in self.container.get_services().items():",
    "            if not service_info.is_running():",
    "                logger.info(\"the workload is not ready (service '%s' is not running)\", name)",
    "                return False",
    "        checks = self.container.get_checks(level=ops.pebble.CheckLevel.READY)",
    "        for check_info in checks.values():",
    "            if check_info.status != ops.pebble.CheckStatus.UP:",
    "                return False",
    "        return True",
    "",
    "    def wait_for_ready(self) -> None:",
    '        """Wait for the workload to be ready to use."""',
    "        for _ in range(3):",
    "            if self.is_ready():",
    "                return",
    "            time.sleep(1)",
    '        logger.error("the workload was not ready within the expected time")',
    '        raise RuntimeError("workload is not ready")',
    "",
    "",
    'if __name__ == "__main__":  # pragma: nocover',
    `    ops.main(${ctx.className})`,
    "",
  ].join("\n");
}

/** Generate a filled src/charm.py from workload analysis. */
export function filledSrcCharmPy(ctx: CharmTemplateContext, analysis: WorkloadAnalysis): string {
  const lines: string[] = [];
  lines.push("#!/usr/bin/env python3");
  lines.push("# Copyright 2026 Ubuntu");
  lines.push("# See LICENSE file for licensing details.");
  lines.push("");
  lines.push('"""Charm for ' + ctx.title + '."""');
  lines.push("");
  lines.push("import logging");
  lines.push("import time");
  lines.push("");
  lines.push("import ops");
  lines.push("");
  lines.push(`import ${ctx.moduleName}`);
  lines.push("");
  lines.push("logger = logging.getLogger(__name__)");
  lines.push("");
  lines.push('SERVICE_NAME = "workload"');
  lines.push('CHECK_NAME = "service-ready"');
  lines.push("");
  lines.push("");
  lines.push(`class ${ctx.className}(ops.CharmBase):`);
  lines.push(`    """Charm for ${ctx.title}."""`);
  lines.push("");
  lines.push("    def __init__(self, framework: ops.Framework):");
  lines.push("        super().__init__(framework)");
  lines.push('        framework.observe(self.on["workload"].pebble_ready, self._on_pebble_ready)');
  lines.push('        self.container = self.unit.get_container("workload")');

  if (analysis.needsDatabase) {
    lines.push('        framework.observe(self.on.database_relation_changed, self._on_database_changed)');
  }
  if (analysis.isWebApp) {
    lines.push('        framework.observe(self.on.ingress_relation_joined, self._on_ingress_joined)');
  }
  lines.push("");

  // _on_pebble_ready
  lines.push("    def _on_pebble_ready(self, event: ops.PebbleReadyEvent):");
  lines.push('        """Handle pebble-ready event."""');
  lines.push('        self.unit.status = ops.MaintenanceStatus("starting workload")');

  // Build env map
  if (analysis.envVars && Object.keys(analysis.envVars).length > 0) {
    lines.push("        env = {");
    for (const [key, _val] of Object.entries(analysis.envVars)) {
      const configKey = key.toLowerCase().replace(/_/g, "-");
      lines.push(`            "${key}": self.config.get("${configKey}", "${_val}"),`);
    }
    lines.push("        }");
  }

  lines.push("        layer: ops.pebble.LayerDict = {");
  lines.push('            "services": {');
  lines.push("                SERVICE_NAME: {");
  lines.push('                    "override": "replace",');
  lines.push(`                    "summary": "${ctx.title} service",`);
  lines.push(`                    "command": "${analysis.command}",`);
  lines.push('                    "startup": "enabled",');
  if (analysis.envVars && Object.keys(analysis.envVars).length > 0) {
    lines.push('                    "environment": env,');
  }
  lines.push("                },");
  lines.push("            },");
  if (analysis.port) {
    lines.push('            "checks": {');
    lines.push("                CHECK_NAME: {");
    lines.push('                    "override": "replace",');
    lines.push('                    "level": "ready",');
    lines.push('                    "http": {');
    lines.push(`                        "url": "http://localhost:${analysis.port}",`);
    lines.push("                    },");
    lines.push("                },");
    lines.push("            },");
  }
  lines.push("        }");
  lines.push('        self.container.add_layer("workload", layer, combine=True)');
  lines.push("        self.container.replan()");
  lines.push("        self.wait_for_ready()");
  lines.push(`        version = ${ctx.moduleName}.get_version()`);
  lines.push("        if version is not None:");
  lines.push("            self.unit.set_workload_version(version)");
  lines.push("        self.unit.status = ops.ActiveStatus()");
  lines.push("");

  // Relations
  if (analysis.needsDatabase) {
    lines.push("    def _on_database_changed(self, event: ops.RelationChangedEvent) -> None:");
    lines.push('        """Handle database relation changes."""');
    lines.push("        if not event.relation.data.get(event.app):");
    lines.push("            return");
    lines.push("        # TODO: configure workload with database credentials");
    lines.push("");
  }

  if (analysis.isWebApp) {
    lines.push("    def _on_ingress_joined(self, event: ops.RelationJoinedEvent) -> None:");
    lines.push('        """Handle ingress relation."""');
    lines.push("        if not self.unit.is_leader():");
    lines.push("            return");
    lines.push('        event.relation.data[self.app]["url"] = f"http://{self.app.name}:{str(self.config.get("port", ' + String(analysis.port) + '))}"');
    lines.push("");
  }

  // Readiness helpers
  lines.push("    def is_ready(self) -> bool:");
  lines.push('        """Check whether the workload is ready to use."""');
  lines.push("        for name, service_info in self.container.get_services().items():");
  lines.push("            if not service_info.is_running():");
  lines.push("                logger.info(\"the workload is not ready (service '%s' is not running)\", name)");
  lines.push("                return False");
  lines.push("        checks = self.container.get_checks(level=ops.pebble.CheckLevel.READY)");
  lines.push("        for check_info in checks.values():");
  lines.push("            if check_info.status != ops.pebble.CheckStatus.UP:");
  lines.push("                return False");
  lines.push("        return True");
  lines.push("");
  lines.push("    def wait_for_ready(self) -> None:");
  lines.push('        """Wait for the workload to be ready to use."""');
  lines.push("        for _ in range(3):");
  lines.push("            if self.is_ready():");
  lines.push("                return");
  lines.push("            time.sleep(1)");
  lines.push('        logger.error("the workload was not ready within the expected time")');
  lines.push('        raise RuntimeError("workload is not ready")');
  lines.push("");
  lines.push("");
  lines.push('if __name__ == "__main__":  # pragma: nocover');
  lines.push(`    ops.main(${ctx.className})`);
  lines.push("");

  return lines.join("\n");
}

// ── File templates (original, full scaffold) ────────────────────────────────

export function gitignore(): string {
  return [
    "venv/",
    "build/",
    "*.charm",
    ".tox/",
    ".coverage",
    "__pycache__/",
    "*.py[cod]",
    ".idea",
    ".vscode/",
    "",
  ].join("\n");
}

export function contributing(): string {
  return [
    "# Contributing",
    "",
    "To make contributions to this charm, you'll need a working",
    "[development setup](https://documentation.ubuntu.com/juju/3.6/howto/manage-your-deployment/#set-up-your-deployment-local-testing-and-development).",
    "",
    "You can create an environment for development with `tox`:",
    "",
    "```shell",
    "tox devenv -e integration",
    "source venv/bin/activate",
    "```",
    "",
    "## Testing",
    "",
    "This project uses `tox` for managing test environments. There are some pre-configured environments",
    "that can be used for linting and formatting code when you're preparing contributions to the charm:",
    "",
    "```shell",
    "tox run -e format        # update your code according to linting rules",
    "tox run -e lint          # code style",
    "tox run -e static        # static type checking",
    "tox run -e unit          # unit tests",
    "tox run -e integration   # integration tests",
    "tox                      # runs 'format', 'lint', 'static', and 'unit' environments",
    "```",
    "",
    "## Build the charm",
    "",
    "Build the charm in this git repository using:",
    "",
    "```shell",
    "charmcraft pack",
    "```",
    "",
  ].join("\n");
}

export function license(): string {
  return [
    "                                 Apache License",
    "                           Version 2.0, January 2004",
    "                        http://www.apache.org/licenses/",
    "",
    "   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION",
    "",
    "   1. Definitions.",
    '',
    '      "License" shall mean the terms and conditions for use, reproduction,',
    "      and distribution as defined by Sections 1 through 9 of this document.",
    '',
    '      "Licensor" shall mean the copyright owner or entity authorized by',
    "      the copyright owner that is granting the License.",
    '',
    '      "Legal Entity" shall mean the union of the acting entity and all',
    "      other entities that control, are controlled by, or are under common",
    '      control with that entity. For the purposes of this definition,',
    '      "control" means (i) the power, direct or indirect, to cause the',
    "      direction or management of such entity, whether by contract or",
    '      otherwise, or (ii) ownership of fifty percent (50%) or more of the',
    '      outstanding shares, or (iii) beneficial ownership of such entity.',
    '',
    '      "You" (or "Your") shall mean an individual or Legal Entity',
    "      exercising permissions granted by this License.",
    '',
    '      "Source" form shall mean the preferred form for making modifications,',
    "      including but not limited to software source code, documentation",
    "      source, and configuration files.",
    '',
    '      "Object" form shall mean any form resulting from mechanical',
    "      transformation or translation of a Source form, including but",
    "      not limited to compiled object code, generated documentation,",
    "      and conversions to other media types.",
    '',
    '      "Work" shall mean the work of authorship, whether in Source or',
    "      Object form, made available under the License, as indicated by a",
    "      copyright notice that is included in or attached to the work",
    "      (an example is provided in the Appendix below).",
    '',
    '      "Derivative Works" shall mean any work, whether in Source or Object',
    "      form, that is based on (or derived from) the Work and for which the",
    "      editorial revisions, annotations, elaborations, or other modifications",
    "      represent, as a whole, an original work of authorship. For the purposes",
    "      of this License, Derivative Works shall not include works that remain",
    "      separable from, or merely link (or bind by name) to the interfaces of,",
    "      the Work and Derivative Works thereof.",
    '',
    '      "Contribution" shall mean any work of authorship, including',
    "      the original version of the Work and any modifications or additions",
    "      to that Work or Derivative Works thereof, that is intentionally",
    "      submitted to Licensor for inclusion in the Work by the copyright owner",
    '      or by an individual or Legal Entity authorized to submit on behalf of',
    '      the copyright owner. For the purposes of this definition, "submitted"',
    "      means any form of electronic, verbal, or written communication sent",
    "      to the Licensor or its representatives, including but not limited to",
    "      communication on electronic mailing lists, source code control systems,",
    "      and issue tracking systems that are managed by, or on behalf of the,",
    "      Licensor for the purpose of discussing and improving the Work, but",
    "      excluding communication that is conspicuously marked or otherwise",
    '      designated in writing by the copyright owner as "Not a Contribution."',
    '',
    '      "Contributor" shall mean Licensor and any individual or Legal Entity',
    "      on behalf of whom a Contribution has been received by Licensor and",
    "      subsequently incorporated within the Work.",
    "",
    "   2. Grant of Copyright License. Subject to the terms and conditions of",
    "      this License, each Contributor hereby grants to You a perpetual,",
    "      worldwide, non-exclusive, no-charge, royalty-free, irrevocable",
    "      copyright license to reproduce, prepare Derivative Works of,",
    "      publicly display, publicly perform, sublicense, and distribute the",
    "      Work and such Derivative Works in Source or Object form.",
    "",
    "   3. Grant of Patent License. Subject to the terms and conditions of",
    "      this License, each Contributor hereby grants to You a perpetual,",
    "      worldwide, non-exclusive, no-charge, royalty-free, irrevocable",
    "      (except as stated in this section) patent license to make, have made,",
    "      use, offer to sell, sell, import, and otherwise transfer the Work,",
    "      where such license applies only to those patent claims licensable",
    "      by such Contributor that are necessarily infringed by their",
    "      Contribution(s) alone or by combination of their Contribution(s)",
    "      with the Work to which such Contribution(s) was submitted. If You",
    "      institute patent litigation against any entity (including a",
    "      cross-claim or counterclaim in a lawsuit) alleging that the Work",
    "      or a Contribution incorporated within the Work constitutes direct",
    "      or contributory patent infringement, then any patent licenses",
    "      granted to You under this License for that Work shall terminate",
    "      as of the date such litigation is filed.",
    "",
    "   4. Redistribution. You may reproduce and distribute copies of the",
    "      Work or Derivative Works thereof in any medium, with or without",
    "      modifications, and in Source or Object form, provided that You",
    "      meet the following conditions:",
    "",
    "      (a) You must give any other recipients of the Work or",
    "          Derivative Works a copy of this License; and",
    "",
    "      (b) You must cause any modified files to carry prominent notices",
    "          stating that You changed the files; and",
    "",
    "      (c) You must retain, in the Source form of any Derivative Works",
    "          that You distribute, all copyright, patent, trademark, and",
    "          attribution notices from the Source form of the Work,",
    "          excluding those notices that do not pertain to any part of",
    "          the Derivative Works; and",
    "",
    '      (d) If the Work includes a "NOTICE" text file as part of its',
    "          distribution, then any Derivative Works that You distribute must",
    "          include a readable copy of the attribution notices contained",
    "          within such NOTICE file, excluding those notices that do not",
    "          pertain to any part of the Derivative Works, in at least one",
    "          of the following places: within a NOTICE text file distributed",
    "          as part of the Derivative Works; within the Source form or",
    "          documentation, if provided along with the Derivative Works; or,",
    "          within a display generated by the Derivative Works, if and",
    "          wherever such third-party notices normally appear. The contents",
    "          of the NOTICE file are for informational purposes only and",
    "          do not modify the License. You may add Your own attribution",
    "          notices within Derivative Works that You distribute, alongside",
    "          or as an addendum to the NOTICE text from the Work, provided",
    "          that such additional attribution notices cannot be construed",
    "          as modifying the License.",
    "",
    "      You may add Your own copyright statement to Your modifications and",
    "      may provide additional or different license terms and conditions",
    "      for use, reproduction, or distribution of Your modifications, or",
    "      for any such Derivative Works as a whole, provided Your use,",
    "      reproduction, and distribution of the Work otherwise complies with",
    "      the conditions stated in this License.",
    "",
    "   5. Submission of Contributions. Unless You explicitly state otherwise,",
    "      any Contribution intentionally submitted for inclusion in the Work",
    "      by You to the Licensor shall be under the terms and conditions of",
    "      this License, without any additional terms or conditions.",
    "      Notwithstanding the above, nothing herein shall supersede or modify",
    "      the terms of any separate license agreement you may have executed",
    "      with Licensor regarding such Contributions.",
    "",
    "   6. Trademarks. This License does not grant permission to use the trade",
    "      names, trademarks, service marks, or product names of the Licensor,",
    "      except as required for reasonable and customary use in describing the",
    '      origin of the Work and reproducing the content of the NOTICE file.',
    "",
    "   7. Disclaimer of Warranty. Unless required by applicable law or",
    '      agreed to in writing, Licensor provides the Work (and each',
    '      Contributor provides its Contributions) on an "AS IS" BASIS,',
    "      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or",
    "      implied, including, without limitation, any warranties or conditions",
    "      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A",
    "      PARTICULAR PURPOSE. You are solely responsible for determining the",
    "      appropriateness of using or redistributing the Work and assume any",
    "      risks associated with Your exercise of permissions under this License.",
    "",
    "   8. Limitation of Liability. In no event and under no legal theory,",
    "      whether in tort (including negligence), contract, or otherwise,",
    "      unless required by applicable law (such as deliberate and grossly",
    "      negligent acts) or agreed to in writing, shall any Contributor be",
    "      liable to You for damages, including any direct, indirect, special,",
    "      incidental, or consequential damages of any character arising as a",
    "      result of this License or out of the use or inability to use the",
    "      Work (including but not limited to damages for loss of goodwill,",
    "      work stoppage, computer failure or malfunction, or any and all",
    "      other commercial damages or losses), even if such Contributor",
    "      has been advised of the possibility of such damages.",
    "",
    "   9. Accepting Warranty or Additional Liability. While redistributing",
    "      the Work or Derivative Works thereof, You may choose to offer,",
    "      and charge a fee for, acceptance of support, warranty, indemnity,",
    "      or other liability obligations and/or rights consistent with this",
    "      License. However, in accepting such obligations, You may act only",
    "      on Your own behalf and on Your sole responsibility, not on behalf",
    "      of any other Contributor, and only if You agree to indemnify,",
    "      defend, and hold each Contributor harmless for any liability",
    "      incurred by, or claims asserted against, such Contributor by reason",
    "      of your accepting any such warranty or additional liability.",
    "",
    "   END OF TERMS AND CONDITIONS",
    "",
    "   APPENDIX: How to apply the Apache License to your work.",
    "",
    "      To apply the Apache License to your work, attach the following",
    '      boilerplate notice, with the fields enclosed by brackets "[]"',
    "      replaced with your own identifying information. (Don't include",
    "      the brackets!)  The text should be enclosed in the appropriate",
    "      comment syntax for the file format. We also recommend that a",
    "      file or class name and description of purpose be included on the",
    '      same "printed page" as the copyright notice for easier',
    "      identification within third-party archives.",
    "",
    "   Copyright 2026 Ubuntu",
    "",
    '   Licensed under the Apache License, Version 2.0 (the "License");',
    "   you may not use this file except in compliance with the License.",
    "   You may obtain a copy of the License at",
    "",
    "       http://www.apache.org/licenses/LICENSE-2.0",
    "",
    "   Unless required by applicable law or agreed to in writing, software",
    '   distributed under the License is distributed on an "AS IS" BASIS,',
    "   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.",
    "   See the License for the specific language governing permissions and",
    "   limitations under the License.",
    "",
  ].join("\n");
}

export function readme(ctx: CharmTemplateContext): string {
  return [
    "<!--",
    "Avoid using this README file for information that is maintained or published elsewhere, e.g.:",
    "",
    "* charmcraft.yaml > published on Charmhub",
    "* documentation > published on (or linked to from) Charmhub",
    "* detailed contribution guide > documentation or CONTRIBUTING.md",
    "",
    "Use links instead.",
    "-->",
    "",
    `# ${ctx.charmName}`,
    "",
    `Charmhub package name: ${ctx.charmName}`,
    `More information: https://charmhub.io/${ctx.charmName}`,
    "",
    "Describe your charm in one or two sentences.",
    "",
    "## Other resources",
    "",
    "<!-- If your charm is documented somewhere else other than Charmhub, provide a link separately. -->",
    "",
    "- [Read more](https://example.com)",
    "",
    "- [Contributing](CONTRIBUTING.md) <!-- or link to other contribution documentation -->",
    "",
    "- See the [Juju documentation](https://documentation.ubuntu.com/juju/3.6/howto/manage-charms/) for more information about developing and improving charms.",
    "",
  ].join("\n");
}

export function charmcraftYaml(ctx: CharmTemplateContext): string {
  return [
    "# This file configures Charmcraft.",
    "# See https://documentation.ubuntu.com/charmcraft/stable/reference/files/charmcraft-yaml-file/",
    "type: charm",
    `name: ${ctx.charmName}`,
    `title: ${ctx.title} Charm`,
    "summary: A very short one-line summary of the charm.",
    "description: |",
    "  A single sentence that says what the charm is, concisely and memorably.",
    "",
    "  A paragraph of one to three short sentences, that describe what the charm does.",
    "",
    "  A third paragraph that explains what need the charm meets.",
    "",
    "  Finally, a paragraph that describes whom the charm is useful for.",
    "",
    "# Documentation:",
    "# https://documentation.ubuntu.com/charmcraft/stable/howto/build-guides/select-platforms/",
    "base: ubuntu@22.04",
    "platforms:",
    "  amd64:",
    "  arm64:",
    "",
    "parts:",
    "  charm:",
    "    plugin: uv",
    "    source: .",
    "    build-snaps:",
    "      - astral-uv",
    "",
    "config:",
    "  options:",
    "    log-level:",
    "      description: |",
    '        Configures the log level of the workload.',
    "",
    '        Acceptable values are: "info", "debug", "warning", "error" and "critical"',
    '      default: "info"',
    "      type: string",
    "",
    "containers:",
    "  some-container:",
    "    resource: some-container-image",
    "",
    "resources:",
    "  some-container-image:",
    "    type: oci-image",
    "    description: OCI image for the 'some-container' container",
    "    upstream-source: some-repo/some-image:some-tag",
    "",
  ].join("\n");
}

export function pyprojectToml(ctx: CharmTemplateContext): string {
  return [
    "# Copyright 2026 Ubuntu",
    "# See LICENSE file for licensing details.",
    "",
    "[project]",
    `name = "${ctx.charmName}"`,
    'version = "0.0.1"',
    'requires-python = ">=3.10"',
    "",
    "dependencies = [",
    '    "ops>=3,<4",',
    "]",
    "",
    "[dependency-groups]",
    "lint = [",
    '    "ruff",',
    '    "codespell",',
    '    "pyright",',
    "]",
    "unit = [",
    '    "coverage[toml]",',
    '    "ops[testing]",',
    '    "pytest",',
    "]",
    "integration = [",
    '    "jubilant",',
    '    "pytest",',
    '    "PyYAML",',
    "]",
    "",
    "# Testing tools configuration",
    "[tool.coverage.run]",
    "branch = true",
    "",
    "[tool.coverage.report]",
    "show_missing = true",
    "",
    "[tool.pytest.ini_options]",
    'minversion = "6.0"',
    'log_cli_level = "INFO"',
    "",
    "# Linting tools configuration",
    "[tool.ruff]",
    "line-length = 99",
    'lint.select = ["E", "W", "F", "C", "N", "D", "I001"]',
    "lint.ignore = [",
    '    "D105",',
    '    "D107",',
    '    "D203",',
    '    "D204",',
    '    "D213",',
    '    "D215",',
    '    "D400",',
    '    "D404",',
    '    "D406",',
    '    "D407",',
    '    "D408",',
    '    "D409",',
    '    "D413",',
    "]",
    'extend-exclude = ["__pycache__", "*.egg_info"]',
    'lint.per-file-ignores = {"tests/*" = ["D100","D101","D102","D103","D104"]}',
    "",
    "[tool.ruff.lint.mccabe]",
    "max-complexity = 10",
    "",
    "[tool.codespell]",
    'skip = "build,lib,venv,icon.svg,.tox,.git,.mypy_cache,.ruff_cache,.coverage"',
    "",
    "[tool.pyright]",
    'include = ["src", "tests"]',
    "",
  ].join("\n");
}

export function srcCharmPy(ctx: CharmTemplateContext): string {
  return [
    "#!/usr/bin/env python3",
    "# Copyright 2026 Ubuntu",
    "# See LICENSE file for licensing details.",
    "",
    '"""Charm the application."""',
    "",
    "import logging",
    "import time",
    "",
    "import ops",
    "",
    `import ${ctx.moduleName}`,
    "",
    "logger = logging.getLogger(__name__)",
    "",
    'SERVICE_NAME = "some-service"',
    "",
    "",
    `class ${ctx.className}(ops.CharmBase):`,
    '    """Charm the application."""',
    "",
    "    def __init__(self, framework: ops.Framework):",
    "        super().__init__(framework)",
    '        framework.observe(self.on["some_container"].pebble_ready, self._on_pebble_ready)',
    '        self.container = self.unit.get_container("some-container")',
    "",
    "    def _on_pebble_ready(self, event: ops.PebbleReadyEvent):",
    '        """Handle pebble-ready event."""',
    '        self.unit.status = ops.MaintenanceStatus("starting workload")',
    "        layer: ops.pebble.LayerDict = {",
    '            "services": {',
    "                SERVICE_NAME: {",
    '                    "override": "replace",',
    '                    "summary": "A service that runs in the workload container",',
    '                    "command": "/bin/foo",  # Change this!',
    '                    "startup": "enabled",',
    "                }",
    "            }",
    "        }",
    '        self.container.add_layer("base", layer, combine=True)',
    "        self.container.replan()",
    "        self.wait_for_ready()",
    `        version = ${ctx.moduleName}.get_version()`,
    "        if version is not None:",
    "            self.unit.set_workload_version(version)",
    "        self.unit.status = ops.ActiveStatus()",
    "",
    "    def is_ready(self) -> bool:",
    '        """Check whether the workload is ready to use."""',
    "        for name, service_info in self.container.get_services().items():",
    "            if not service_info.is_running():",
    "                logger.info(\"the workload is not ready (service '%s' is not running)\", name)",
    "                return False",
    "        checks = self.container.get_checks(level=ops.pebble.CheckLevel.READY)",
    "        for check_info in checks.values():",
    "            if check_info.status != ops.pebble.CheckStatus.UP:",
    "                return False",
    "        return True",
    "",
    "    def wait_for_ready(self) -> None:",
    '        """Wait for the workload to be ready to use."""',
    "        for _ in range(3):",
    "            if self.is_ready():",
    "                return",
    "            time.sleep(1)",
    '        logger.error("the workload was not ready within the expected time")',
    '        raise RuntimeError("workload is not ready")',
    "",
    "",
    'if __name__ == "__main__":  # pragma: nocover',
    `    ops.main(${ctx.className})`,
    "",
  ].join("\n");
}

export function srcWorkloadPy(ctx: CharmTemplateContext): string {
  return [
    "# Copyright 2026 Ubuntu",
    "# See LICENSE file for licensing details.",
    "",
    '"""Functions for interacting with the workload.',
    "",
    "The intention is that this module could be used outside the context of a charm.",
    '"""',
    "",
    "import logging",
    "",
    "logger = logging.getLogger(__name__)",
    "",
    "",
    "# Functions for interacting with the workload, for example over HTTP:",
    "",
    "",
    "def get_version() -> str | None:",
    '    """Get the running version of the workload."""',
    "    # You'll need to implement this function (or remove it if not needed).",
    "    return None",
    "",
  ].join("\n");
}

export function unitTestCharm(ctx: CharmTemplateContext): string {
  return [
    "# Copyright 2026 Ubuntu",
    "# See LICENSE file for licensing details.",
    "#",
    "# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/",
    "",
    "import pytest",
    "from ops import pebble, testing",
    "",
    `from charm import CHECK_NAME, SERVICE_NAME, ${ctx.className}`,
    "",
    "layer = pebble.Layer(",
    "    {",
    '        "services": {',
    "            SERVICE_NAME: {",
    '                "override": "replace",',
    '                "command": "/bin/foo",',
    '                "startup": "enabled",',
    "            }",
    "        },",
    '        "checks": {',
    "            CHECK_NAME: {",
    '                "override": "replace",',
    '                "level": "ready",',
    '                "threshold": 3,',
    '                "startup": "enabled",',
    '                "http": {',
    '                    "url": "http://localhost:8000/version",',
    "                },",
    "            }",
    "        },",
    "    }",
    ")",
    "",
    "",
    "def mock_get_version():",
    '    """Get a mock version string without executing the workload code."""',
    '    return "1.0.0"',
    "",
    "",
    "def test_pebble_ready(monkeypatch: pytest.MonkeyPatch):",
    '    """Test that the charm has the correct state after handling the pebble-ready event."""',
    "    # Arrange:",
    `    ctx = testing.Context(${ctx.className})`,
    "    check_in = testing.CheckInfo(",
    "        CHECK_NAME,",
    "        level=pebble.CheckLevel.READY,",
    "        status=pebble.CheckStatus.UP,",
    "    )",
    "    container_in = testing.Container(",
    '        "some-container",',
    "        can_connect=True,",
    '        layers={"base": layer},',
    '        service_statuses={SERVICE_NAME: pebble.ServiceStatus.INACTIVE},',
    '        check_infos={check_in},',
    "    )",
    "    state_in = testing.State(containers={container_in})",
    `    monkeypatch.setattr("charm.${ctx.moduleName}.get_version", mock_get_version)`,
    "",
    "    # Act:",
    "    state_out = ctx.run(ctx.on.pebble_ready(container_in), state_in)",
    "",
    "    # Assert:",
    "    container_out = state_out.get_container(container_in.name)",
    "    assert container_out.service_statuses[SERVICE_NAME] == pebble.ServiceStatus.ACTIVE",
    "    assert state_out.workload_version is not None",
    "    assert state_out.unit_status == testing.ActiveStatus()",
    "",
    "",
    "def test_pebble_ready_service_not_ready():",
    '    """Test that the charm raises an error if the workload isn\'t ready after Pebble starts it."""',
    "    # Arrange:",
    `    ctx = testing.Context(${ctx.className})`,
    "    check_in = testing.CheckInfo(",
    "        CHECK_NAME,",
    "        level=pebble.CheckLevel.READY,",
    "        status=pebble.CheckStatus.DOWN,",
    "    )",
    "    container_in = testing.Container(",
    '        "some-container",',
    "        can_connect=True,",
    '        layers={"base": layer},',
    '        service_statuses={SERVICE_NAME: pebble.ServiceStatus.INACTIVE},',
    '        check_infos={check_in},',
    "    )",
    "    state_in = testing.State(containers={container_in})",
    "",
    "    # Act & assert:",
    "    with pytest.raises(testing.errors.UncaughtCharmError):",
    "        ctx.run(ctx.on.pebble_ready(container_in), state_in)",
    "",
  ].join("\n");
}

export function integrationConfTest(ctx: CharmTemplateContext): string {
  return [
    "# Copyright 2026 Ubuntu",
    "# See LICENSE file for licensing details.",
    "#",
    "# The integration tests use the Jubilant library. See https://documentation.ubuntu.com/jubilant/",
    "# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/",
    "",
    "import logging",
    "import os",
    "import pathlib",
    "import sys",
    "import time",
    "",
    "import jubilant",
    "import pytest",
    "",
    "logger = logging.getLogger(__name__)",
    "",
    "",
    '@pytest.fixture(scope="module")',
    "def juju(request: pytest.FixtureRequest):",
    '    """Create a temporary Juju model for running tests."""',
    "    with jubilant.temp_model() as juju:",
    "        yield juju",
    "",
    "        if request.session.testsfailed:",
    '            logger.info("Collecting Juju logs...")',
    "            time.sleep(0.5)",
    "            log = juju.debug_log(limit=1000)",
    '            print(log, end="", file=sys.stderr)',
    "",
    "",
    '@pytest.fixture(scope="session")',
    "def charm():",
    '    """Return the path of the charm under test."""',
    '    if "CHARM_PATH" in os.environ:',
    '        charm_path = pathlib.Path(os.environ["CHARM_PATH"])',
    "        if not charm_path.exists():",
    "            raise FileNotFoundError(f\"Charm does not exist: {charm_path}\")",
    "        return charm_path",
    '    charm_paths = list(pathlib.Path(".").glob("*.charm"))',
    "    if not charm_paths:",
    '        raise FileNotFoundError("No .charm file in current directory")',
    "    if len(charm_paths) > 1:",
    '        path_list = ", ".join(str(path) for path in charm_paths)',
    "        raise ValueError(f\"More than one .charm file in current directory: {path_list}\")",
    "    return charm_paths[0]",
    "",
  ].join("\n");
}

export function integrationTestCharm(ctx: CharmTemplateContext): string {
  return [
    "# Copyright 2026 Ubuntu",
    "# See LICENSE file for licensing details.",
    "#",
    "# The integration tests use the Jubilant library. See https://documentation.ubuntu.com/jubilant/",
    "# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/",
    "",
    "import logging",
    "import pathlib",
    "",
    "import jubilant",
    "import pytest",
    "import yaml",
    "",
    "logger = logging.getLogger(__name__)",
    "",
    'METADATA = yaml.safe_load(pathlib.Path("charmcraft.yaml").read_text())',
    "",
    "",
    "def test_deploy(charm: pathlib.Path, juju: jubilant.Juju):",
    '    """Deploy the charm under test."""',
    "    resources = {",
    '        "some-container-image": METADATA["resources"]["some-container-image"]["upstream-source"]',
    "    }",
    `    juju.deploy(charm.resolve(), app="${ctx.charmName}", resources=resources)`,
    "    juju.wait(jubilant.all_active)",
    "",
    "",
    '@pytest.mark.skip(reason="test.get_version is not implemented")',
    "def test_workload_version_is_set(charm: pathlib.Path, juju: jubilant.Juju):",
    '    """Check that the correct version of the workload is running."""',
    `    version = juju.status().apps["${ctx.charmName}"].version`,
    '    assert version == "3.14"  # Replace 3.14 by the expected version of the workload.',
    "",
  ].join("\n");
}

export function toxIni(_ctx: CharmTemplateContext): string {
  return [
    "# Copyright 2026 Ubuntu",
    "# See LICENSE file for licensing details.",
    "",
    "[tox]",
    "no_package = True",
    "skip_missing_interpreters = True",
    "env_list = format, lint, unit",
    "min_version = 4.0.0",
    "",
    "[vars]",
    "src_path = {tox_root}/src",
    "tests_path = {tox_root}/tests",
    ";lib_path = {tox_root}/lib/charms/operator_name_with_underscores",
    "all_path = {[vars]src_path} {[vars]tests_path}",
    "",
    "[testenv]",
    "set_env =",
    "    PYTHONPATH = {tox_root}/lib:{[vars]src_path}",
    "    PYTHONBREAKPOINT=pdb.set_trace",
    "    PY_COLORS=1",
    "pass_env =",
    "    PYTHONPATH",
    "    CHARM_BUILD_DIR",
    "    MODEL_SETTINGS",
    "",
    "[testenv:format]",
    "description = Apply coding style standards to code",
    "deps =",
    "    ruff",
    "commands =",
    "    ruff format {[vars]all_path}",
    "    ruff check --fix {[vars]all_path}",
    "",
    "[testenv:lint]",
    "description = Check code against coding style standards, and static checks",
    "runner = uv-venv-lock-runner",
    "dependency_groups =",
    "    lint",
    "    unit",
    "    integration",
    "commands =",
    "    # if this charm owns a lib, uncomment \"lib_path\" variable",
    "    # and uncomment the following line",
    "    # codespell {[vars]lib_path}",
    "    codespell {tox_root}",
    "    ruff check {[vars]all_path}",
    "    ruff format --check --diff {[vars]all_path}",
    "    pyright {posargs}",
    "",
    "[testenv:unit]",
    "description = Run unit tests",
    "runner = uv-venv-lock-runner",
    "dependency_groups =",
    "    unit",
    "commands =",
    "    coverage run --source={[vars]src_path} -m pytest \\",
    "        -v \\",
    "        -s \\",
    "        --tb native \\",
    "        {[vars]tests_path}/unit \\",
    "        {posargs}",
    "    coverage report",
    "",
    "[testenv:integration]",
    "description = Run integration tests",
    "runner = uv-venv-lock-runner",
    "dependency_groups =",
    "    integration",
    "pass_env =",
    "    CHARM_PATH",
    "commands =",
    "    pytest \\",
    "        -v \\",
    "        -s \\",
    "        --tb native \\",
    "        --log-cli-level=INFO \\",
    "        {[vars]tests_path}/integration \\",
    "        {posargs}",
    "",
  ].join("\n");
}

/**
 * All file entries for a charm project (full scaffold).
 * Each entry is [relativePath, content].
 */
export function allFiles(ctx: CharmTemplateContext): Array<[string, string]> {
  return [
    [".gitignore", gitignore()],
    ["CONTRIBUTING.md", contributing()],
    ["LICENSE", license()],
    ["README.md", readme(ctx)],
    ["charmcraft.yaml", charmcraftYaml(ctx)],
    ["pyproject.toml", pyprojectToml(ctx)],
    ["tox.ini", toxIni(ctx)],
    [`src/charm.py`, srcCharmPy(ctx)],
    [`src/${ctx.moduleName}.py`, srcWorkloadPy(ctx)],
    ["tests/__init__.py", ""],
    ["tests/unit/__init__.py", ""],
    ["tests/unit/test_charm.py", unitTestCharm(ctx)],
    ["tests/integration/__init__.py", ""],
    ["tests/integration/conftest.py", integrationConfTest(ctx)],
    ["tests/integration/test_charm.py", integrationTestCharm(ctx)],
  ];
}

/**
 * Skeleton file entries — same scaffold but charmcraft.yaml and src/charm.py
 * use placeholder versions with TODO markers.
 */
export function skeletonFiles(ctx: CharmTemplateContext): Array<[string, string]> {
  return [
    [".gitignore", gitignore()],
    ["CONTRIBUTING.md", contributing()],
    ["LICENSE", license()],
    ["README.md", readme(ctx)],
    ["charmcraft.yaml", skeletonCharmcraftYaml(ctx)],
    ["pyproject.toml", pyprojectToml(ctx)],
    ["tox.ini", toxIni(ctx)],
    [`src/charm.py`, skeletonSrcCharmPy(ctx)],
    [`src/${ctx.moduleName}.py`, srcWorkloadPy(ctx)],
    ["tests/__init__.py", ""],
    ["tests/unit/__init__.py", ""],
    ["tests/unit/test_charm.py", unitTestCharm(ctx)],
    ["tests/integration/__init__.py", ""],
    ["tests/integration/conftest.py", integrationConfTest(ctx)],
    ["tests/integration/test_charm.py", integrationTestCharm(ctx)],
  ];
}

/**
 * Filled file entries — same scaffold but charmcraft.yaml and src/charm.py
 * are generated from workload analysis results.
 */
export function filledFiles(ctx: CharmTemplateContext, analysis: WorkloadAnalysis): Array<[string, string]> {
  return [
    [".gitignore", gitignore()],
    ["CONTRIBUTING.md", contributing()],
    ["LICENSE", license()],
    ["README.md", readme(ctx)],
    ["charmcraft.yaml", filledCharmcraftYaml(ctx, analysis)],
    ["pyproject.toml", pyprojectToml(ctx)],
    ["tox.ini", toxIni(ctx)],
    [`src/charm.py`, filledSrcCharmPy(ctx, analysis)],
    [`src/${ctx.moduleName}.py`, srcWorkloadPy(ctx)],
    ["tests/__init__.py", ""],
    ["tests/unit/__init__.py", ""],
    ["tests/unit/test_charm.py", unitTestCharm(ctx)],
    ["tests/integration/__init__.py", ""],
    ["tests/integration/conftest.py", integrationConfTest(ctx)],
    ["tests/integration/test_charm.py", integrationTestCharm(ctx)],
  ];
}
