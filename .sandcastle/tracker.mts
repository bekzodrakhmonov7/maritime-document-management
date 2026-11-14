// Local-markdown issue tracker for Sandcastle (see docs/agents/issue-tracker.md).
//
// Issues live in `.scratch/<feature>/issues/NN-<slug>.md` with
// `**Status:** <label>` and `**Blocked by:** NN, NN` lines near the top.
//
// `.scratch/` is gitignored, so an agent's edits to issue files inside a
// sandbox worktree are never committed. That's why listing and closing run
// here on the host. The sandbox only gets a read-only copy (copyToWorktree).

import { readFileSync, readdirSync, writeFileSync, existsSync } from "node:fs";
import { join, relative } from "node:path";

const SCRATCH = ".scratch";
const READY = "ready-for-agent";
export const DONE = "done";

const STATUS_RE = /^(\*\*Status:\*\*|Status:)[ \t]*(.+)$/m;
const BLOCKED_RE = /^(?:\*\*Blocked by:\*\*|Blocked by:)[ \t]*(.+)$/m;
const TITLE_RE = /^#\s+(.+)$/m;

export interface Issue {
  /** Feature-qualified id, e.g. "fr-build-plan-01". Used in branch names. */
  id: string;
  /** Ticket number within its feature, e.g. "01". */
  number: string;
  feature: string;
  title: string;
  status: string;
  blockedBy: string[];
  /** Repo-relative, forward-slash path to the issue file. */
  path: string;
  /** Repo-relative path to the feature's spec.md, if one exists. */
  specPath: string | null;
}

/** Expands "01, 03" and "01–13" (en dash or hyphen) into ticket numbers. */
function parseBlockedBy(line: string | undefined): string[] {
  if (!line || /^none\b/i.test(line.trim())) return [];
  const numbers = new Set<string>();
  // Strip parenthesised titles so digits inside them aren't picked up.
  const bare = line.replace(/\([^)]*\)/g, "");
  for (const m of bare.matchAll(/(\d+)\s*[–-]\s*(\d+)|(\d+)/g)) {
    if (m[3]) {
      numbers.add(m[3].padStart(2, "0"));
    } else {
      const from = Number(m[1]);
      const to = Number(m[2]);
      for (let n = from; n <= to; n++) numbers.add(String(n).padStart(2, "0"));
    }
  }
  return [...numbers];
}

const toPosix = (p: string) => p.split("\\").join("/");

export function allIssues(root = process.cwd()): Issue[] {
  const scratch = join(root, SCRATCH);
  if (!existsSync(scratch)) return [];
  const issues: Issue[] = [];
  for (const feature of readdirSync(scratch, { withFileTypes: true })) {
    if (!feature.isDirectory()) continue;
    const issuesDir = join(scratch, feature.name, "issues");
    if (!existsSync(issuesDir)) continue;
    const spec = join(scratch, feature.name, "spec.md");
    for (const file of readdirSync(issuesDir).sort()) {
      const m = /^(\d+)-.+\.md$/.exec(file);
      if (!m) continue;
      const full = join(issuesDir, file);
      const text = readFileSync(full, "utf8");
      issues.push({
        id: `${feature.name}-${m[1]}`,
        number: m[1],
        feature: feature.name,
        title: TITLE_RE.exec(text)?.[1]?.trim() ?? file,
        status: STATUS_RE.exec(text)?.[2]?.trim() ?? "needs-triage",
        blockedBy: parseBlockedBy(BLOCKED_RE.exec(text)?.[1]),
        path: toPosix(relative(root, full)),
        specPath: existsSync(spec) ? toPosix(relative(root, spec)) : null,
      });
    }
  }
  return issues;
}

/**
 * Issues that are `ready-for-agent` and whose every blocker (in the same
 * feature) is `done`. Ready-for-human or untriaged blockers keep an issue
 * blocked.
 */
export function readyIssues(root = process.cwd()): Issue[] {
  const all = allIssues(root);
  const statusOf = new Map(all.map((i) => [`${i.feature}/${i.number}`, i.status]));
  return all.filter(
    (i) =>
      i.status === READY &&
      i.blockedBy.every((n) => statusOf.get(`${i.feature}/${n}`) === DONE),
  );
}

/** Sets the issue's Status line to `done`, keeping its bold/plain style. */
export function closeIssue(issue: Issue, root = process.cwd()): void {
  const full = join(root, issue.path);
  const text = readFileSync(full, "utf8");
  if (!STATUS_RE.test(text)) {
    throw new Error(`No Status line in ${issue.path}`);
  }
  writeFileSync(full, text.replace(STATUS_RE, `$1 ${DONE}`));
}

// `npx tsx .sandcastle/tracker.mts` prints what the planner would see.
if (process.argv[1] && toPosix(process.argv[1]).endsWith(".sandcastle/tracker.mts")) {
  console.log(JSON.stringify(readyIssues(), null, 2));
}
