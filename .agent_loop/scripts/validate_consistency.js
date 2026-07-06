#!/usr/bin/env node
/* validate_consistency.js — Algorithmic-template, naming, circular-ref, and safety-before-execution validator.
 * Emits warnings for things that are technically allowed but suspicious.
 */

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "../..");
const AGENT_DIR = path.join(ROOT, ".agent_loop");

function getAllMdFiles(dir, list = []) {
  const items = fs.readdirSync(dir, { withFileTypes: true });
  for (const item of items) {
    const fullPath = path.join(dir, item.name);
    if (item.isDirectory()) getAllMdFiles(fullPath, list);
    else if (item.name.endsWith(".md")) list.push(fullPath);
  }
  return list;
}

const ALGORITHMIC_SECTIONS = [
  "## Role",
  "## Contract",
  "## Decision Flow",
  "## Failure Modes",
];

const EXPECTED_PARTS = ["Receives", "Returns", "Side effects"];

function warn(result, file, line, message) {
  result.warnings.push({ file, line, message });
}

function fail(result, file, line, message) {
  result.errors.push({ file, line, message });
}

function extractSection(content, marker) {
  const idx = content.indexOf(marker);
  if (idx === -1) return "";
  const start = idx + marker.length;
  const nextSame = content.indexOf("\n## ", start);
  return nextSame === -1 ? content.slice(start) : content.slice(start, nextSame + 1);
}

function lineNumber(content, pos) {
  return content.slice(0, pos).split("\n").length;
}

function normalizeAgentName(filePath, content) {
  const base = path.basename(filePath, ".md");
  const match = content.match(/^#\s+(.+)$/m);
  const declared = match ? match[1].trim() : null;
  return { base, declared };
}

function checkTemplate(agentPath, content, result) {
  if (!/^# .+/m.test(content)) {
    fail(result, agentPath, 1, "Missing required H1 agent name header");
  }
  ALGORITHMIC_SECTIONS.forEach((section) => {
    if (!content.includes(section)) {
      fail(result, agentPath, 1, `Missing required section: ${section}`);
    }
  });

  const contract = extractSection(content, "## Contract");
  EXPECTED_PARTS.forEach((part) => {
    if (!contract.toLowerCase().includes(part.toLowerCase())) {
      warn(result, agentPath, lineNumber(content, content.indexOf("## Contract")), `Contract missing '${part}'`);
    }
  });

  const decision = extractSection(content, "## Decision Flow");
  if (!/\d+\./.test(decision)) {
    warn(result, agentPath, lineNumber(content, content.indexOf("## Decision Flow")), "Decision Flow has no numbered steps");
  }

  const failure = extractSection(content, "## Failure Modes");
  if (!failure.includes("Condition") || !failure.includes("Response")) {
    warn(result, agentPath, lineNumber(content, content.indexOf("## Failure Modes")), "Failure Modes missing Condition/Response table");
  }
}

function checkNaming(agentPath, content, result) {
  const { base, declared } = normalizeAgentName(agentPath, content);
  if (!declared) return;
  const stopWords = new Set(["agent", "the", "a", "an", "and", "or", "of", "for"]);
  const fileWords = base.split("_").map((w) => w.toLowerCase()).filter((w) => w && !stopWords.has(w));
  const declaredWords = declared.split(/\s+/).map((w) => w.toLowerCase().replace(/[^a-z0-9]/g, "")).filter((w) => w && !stopWords.has(w));
  const overlap = fileWords.some((w) => declaredWords.includes(w));
  if (!overlap) {
    warn(result, agentPath, 1, `Agent name '${declared}' looks unrelated to filename '${base}.md'`);
  }
}

function buildGraph(agentPaths) {
  const graph = new Map();
  const files = new Map();
  agentPaths.forEach((p) => {
    const rel = path.relative(ROOT, p).replace(/\\/g, "/");
    const name = path.basename(p, ".md");
    graph.set(name, new Set());
    files.set(name, rel);
  });
  agentPaths.forEach((p) => {
    const content = fs.readFileSync(p, "utf8");
    const fromName = path.basename(p, ".md");
    const linkPattern = /\[([^\]]+)\]\([^)]*\.agent_loop[^)]*\)/g;
    let m;
    while ((m = linkPattern.exec(content)) !== null) {
      const linkedRaw = m[1].replace(/\s+/g, "_").toLowerCase();
      graph.forEach((_, target) => {
        if (target.toLowerCase() === linkedRaw) {
          graph.get(fromName).add(target);
        }
      });
    }
  });
  return { graph, files };
}

function findCycles(graph) {
  const cycles = [];
  const visited = new Set();
  const stack = [];
  const onStack = new Set();

  function dfs(node) {
    visited.add(node);
    stack.push(node);
    onStack.add(node);
    const neighbors = graph.get(node) || new Set();
    neighbors.forEach((next) => {
      if (!visited.has(next)) {
        dfs(next);
      } else if (onStack.has(next)) {
        const idx = stack.indexOf(next);
        cycles.push(stack.slice(idx).concat(next));
      }
    });
    stack.pop();
    onStack.delete(node);
  }

  graph.forEach((_, node) => {
    if (!visited.has(node)) dfs(node);
  });
  return cycles;
}

function canonicalCycle(cycle) {
  const nodes = cycle.slice(0, -1);
  const rotations = Array.from({ length: nodes.length }, (_, i) =>
    nodes.slice(i).concat(nodes.slice(0, i))
  );
  const reversed = [...nodes].reverse();
  const reversedRotations = Array.from({ length: nodes.length }, (_, i) =>
    reversed.slice(i).concat(reversed.slice(0, i))
  );
  const all = rotations.concat(reversedRotations);
  all.sort();
  return all[0].join("→");
}

function findUniqueShortCycles(graph, maxLength = 4) {
  const allCycles = findCycles(graph);
  const seen = new Set();
  const unique = [];
  for (const cycle of allCycles) {
    const length = cycle.length - 1;
    if (length > maxLength) continue;
    const key = canonicalCycle(cycle);
    if (!seen.has(key)) {
      seen.add(key);
      unique.push(cycle);
    }
  }
  return unique;
}

function checkCycles(agentPaths, result) {
  const { graph, files } = buildGraph(agentPaths);
  const cycles = findUniqueShortCycles(graph, 4);
  cycles.forEach((cycle) => {
    const pathStr = cycle.join(" → ");
    const first = cycle[0];
    warn(result, files.get(first), 1, `Circular reference detected: ${pathStr}`);
  });
}

function checkSafetyBeforeExecution(agentPaths, result) {
  const executionDirs = ["tooll_subagents", "tools_read", "tools_replace", "tools_search", "tools_runcom", "tools_runtest", "tools_terminal", "tools_manangr", "tools_database", "tools_web", "tools_memory", "tools_browser", "tools_lighthouse"];
  const safetyMarkers = ["safety_guardrails", "human_oversight"];

  agentPaths.forEach((p) => {
    const dir = path.basename(path.dirname(p));
    if (!executionDirs.includes(dir)) return;
    const content = fs.readFileSync(p, "utf8").replace(/\r\n/g, "\n");
    const decision = extractSection(content, "## Decision Flow").toLowerCase();
    const hasSafety = safetyMarkers.some((m) => decision.includes(m.toLowerCase()));
    if (!hasSafety) {
      warn(result, p, lineNumber(content, content.indexOf("## Decision Flow")), "Execution agent Decision Flow does not reference safety_guardrails or human_oversight");
    }
  });
}

function main() {
  const agentPaths = getAllMdFiles(AGENT_DIR).filter((p) => {
    if (!fs.statSync(p).isFile()) return false;
    const rel = path.relative(AGENT_DIR, p);
    return rel.includes(path.sep) || path.basename(p) === "main_loop.md";
  });

  const result = { errors: [], warnings: [] };

  agentPaths.forEach((p) => {
    const content = fs.readFileSync(p, "utf8").replace(/\r\n/g, "\n");
    checkTemplate(p, content, result);
    checkNaming(p, content, result);
  });

  checkCycles(agentPaths, result);
  checkSafetyBeforeExecution(agentPaths, result);

  if (result.errors.length || result.warnings.length) {
    console.log("Consistency check finished.");
    console.log(`Errors: ${result.errors.length}`);
    result.errors.forEach((e) => console.log(`  ERROR ${e.file}:${e.line} — ${e.message}`));
    console.log(`Warnings: ${result.warnings.length}`);
    result.warnings.forEach((w) => console.log(`  WARN ${w.file}:${w.line} — ${w.message}`));
  } else {
    console.log("All agents consistent. No errors or warnings.");
  }

  process.exit(result.errors.length ? 1 : 0);
}

main();
