// Parallel Planner with Review — four-phase orchestration loop
//
// This template drives a multi-phase workflow:
//   Phase 1 (Plan):             An opus agent analyzes open issues, builds a
//                               dependency graph, and outputs a <plan> JSON
//                               listing unblocked issues with branch names.
//   Phase 2 (Execute + Review): For each issue, a sandbox is created via
//                               createSandbox(). The implementer runs first
//                               (100 iterations). If it produces commits, a
//                               reviewer runs in the same sandbox on the same
//                               branch (1 iteration). All issue pipelines run
//                               concurrently via Promise.allSettled().
//   Phase 3 (Merge):            A single agent merges all completed branches
//                               into the current branch.
//
// The outer loop repeats up to MAX_ITERATIONS times so that newly unblocked
// issues are picked up after each round of merges.
//
// Usage:
//   npx tsx .sandcastle/main.mts
// Or add to package.json:
//   "scripts": { "sandcastle": "npx tsx .sandcastle/main.mts" }

import * as sandcastle from "@ai-hero/sandcastle";
import { docker } from "@ai-hero/sandcastle/sandboxes/docker";
import { z } from "zod";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { closeIssue, readyIssues } from "./tracker.mts";

// Sandcastle copies copyToWorktree paths with the Unix `cp`, which Windows
// lacks. Git for Windows ships one in <git>/usr/bin; append that folder to
// PATH (appended, so Windows' own commands still win) so this script also
// works from PowerShell, not only Git Bash.
if (process.platform === "win32") {
  const gitCore = execFileSync("git", ["--exec-path"], { encoding: "utf8" }).trim();
  const usrBin = join(resolve(gitCore, "..", "..", ".."), "usr", "bin");
  if (existsSync(join(usrBin, "cp.exe"))) {
    process.env.PATH = `${process.env.PATH};${usrBin}`;
  } else {
    console.warn(`cp.exe not found in ${usrBin}; copyToWorktree may fail`);
  }
}
import { agentLog, describeCommits, errorText, note, RUN_DIR, ticket } from "./runlog.mts";

// Model for every phase. Swap to "claude-sonnet-5-5" to cut cost.
const MODEL = "claude-opus-5-5";

// The planner emits its plan as JSON inside <plan> tags; Output.object extracts
// and validates it against this schema. We use Zod here, but any Standard
// Schema validator works just as well — Valibot, ArkType, etc. See
// https://standardschema.dev.
const planSchema = z.object({
  issues: z.array(
    z.object({ id: z.string(), title: z.string(), branch: z.string() }),
  ),
});

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

// Maximum number of plan→execute→merge cycles before stopping.
// Raise this if your backlog is large; lower it for a quick smoke-test run.
// With at most MAX_PARALLEL issues per cycle, 16 agent issues need 8+ cycles.
const MAX_ITERATIONS = 20;

// Most issues worked at the same time (one sandbox each). Extra unblocked
// issues wait for the next cycle. Set to 1 for fully sequential runs.
const MAX_PARALLEL = 2;

// Every ticket's work goes on `faet/<ticket-id>`, e.g. faet/fr-build-plan-01.
const BRANCH_PREFIX = "faet/";

// Identifies this run in merge-branch names, e.g. 20261114-193849.
const RUN_ID = new Date().toISOString().slice(0, 19).replace(/[-:]/g, "").replace("T", "-");

const git = (...args: string[]) =>
  execFileSync("git", args, { encoding: "utf8" }).trim();

// Linux-only folders the hooks create in the worktree. Their symlinks can't
// be deleted by Windows git, so remove them from inside the container first.
async function closeSandbox(sandbox: sandcastle.Sandbox): Promise<void> {
  try {
    await sandbox.exec("rm -rf .venv frontend/node_modules");
  } catch {
    // The container may already be gone; close() still tries to clean up.
  }
  await sandbox.close();
}

// Hooks run inside the sandbox before the agent starts. Dependencies are
// installed fresh in Linux; the host's .venv and node_modules are Windows
// builds and wouldn't work in the container.
// `sandbox-db reset` gives each sandbox its own Postgres (see
// .sandcastle/db/sandbox-db) with the migrations and seed applied. A failing
// migration mustn't stop the sandbox from starting: the agent sees the error
// when it runs the reset itself.
//
// Sandcastle kills a hook after 60 s by default; a cold `npm ci` or `uv sync`
// in a fresh container can take several minutes, so each gets its own limit.
const MINUTE = 60_000;
const hooks = {
  sandbox: {
    onSandboxReady: [
      { command: "sandbox-db reset || echo 'sandbox-db reset failed'", timeoutMs: 5 * MINUTE },
      { command: "uv sync", timeoutMs: 10 * MINUTE },
      { command: "npm --prefix frontend ci", timeoutMs: 15 * MINUTE },
    ],
  },
};

// Gitignored context the agents need to read. These are copies: edits made
// to them inside the sandbox are discarded, so issues are closed on the host.
const copyToWorktree = [".scratch", "docs", "CLAUDE.md", "GLOSSARY.md"];

// ---------------------------------------------------------------------------
// Main loop
// ---------------------------------------------------------------------------

note(`Logs for this run: ${RUN_DIR}`);

for (let iteration = 1; iteration <= MAX_ITERATIONS; iteration++) {
  note(`=== Round ${iteration}/${MAX_ITERATIONS} ===`);

  // -------------------------------------------------------------------------
  // Phase 1: Plan
  //
  // The planning agent (opus, for deeper reasoning) reads the open issue list,
  // builds a dependency graph, and selects the issues that can be worked in
  // parallel right now (i.e., no blocking dependencies on other open issues).
  //
  // It outputs a <plan> JSON block — Output.object parses and validates it.
  // -------------------------------------------------------------------------
  // Ready = `ready-for-agent` with every `Blocked by` ticket already `done`.
  const ready = readyIssues();
  if (ready.length === 0) {
    note("No ready-for-agent issues with all blockers done. Exiting.");
    break;
  }
  note(`Ready: ${ready.map((i) => i.id).join(", ")}`);
  const readyById = new Map(ready.map((i) => [i.id, i]));
  const issuesJson = JSON.stringify(
    ready.map((i) => ({
      id: i.id,
      title: i.title,
      path: i.path,
      body: readFileSync(i.path, "utf8"),
    })),
    null,
    2,
  );

  // No hooks: the planner only reads, so it skips the database and installs.
  const plan = await sandcastle.run({
    sandbox: docker(),
    name: "planner",
    logging: agentLog(iteration, "planner", "planner"),
    // Docker's default "head" mode bind-mounts your real project folder;
    // a worktree keeps the sandbox off it (and allows copyToWorktree).
    branchStrategy: { type: "merge-to-head" },
    copyToWorktree,
    // One iteration is enough: the planner just needs to read and reason,
    // not write code. (Structured output requires maxIterations: 1.)
    maxIterations: 1,
    agent: sandcastle.claudeCode(MODEL),
    promptFile: "./.sandcastle/plan-prompt.md",
    promptArgs: { ISSUES_JSON: issuesJson, MAX_PARALLEL },
    // Extract and validate the <plan> JSON into a typed object. Throws
    // StructuredOutputError if the tag is missing, the JSON is malformed, or
    // validation fails — which aborts the loop.
    output: sandcastle.Output.object({ tag: "plan", schema: planSchema }),
  });

  // Drop anything the planner invented that isn't actually ready, then keep
  // only the first MAX_PARALLEL (the planner lists them in priority order).
  // Branch names are set here, not by the planner, so loop work always lives
  // on `faet/<ticket-id>` (the typo is deliberate: it keeps agent branches
  // apart from hand-written ones) and re-planning reuses the same branch.
  const issues = plan.output.issues
    .filter((i) => readyById.has(i.id))
    .slice(0, MAX_PARALLEL)
    .map((i) => ({ ...i, branch: `${BRANCH_PREFIX}${i.id}` }));

  if (issues.length === 0) {
    // No unblocked work — either everything is done or everything is blocked.
    note("No unblocked issues to work on. Exiting.");
    break;
  }

  note(`Planning complete. ${issues.length} issue(s) this round.`);
  for (const issue of issues) {
    ticket(issue.id, `Round ${iteration}: planned "${issue.title}" on ${issue.branch}`);
  }

  // -------------------------------------------------------------------------
  // Phase 2: Execute + Review
  //
  // For each issue, create a sandbox via createSandbox() so the implementer
  // and reviewer share the same sandbox instance per branch. The implementer
  // runs first; if it produces commits, the reviewer runs in the same sandbox.
  //
  // Promise.allSettled means one failing pipeline doesn't cancel the others.
  // -------------------------------------------------------------------------

  const settled = await Promise.allSettled(
    issues.map(async (issue) => {
      ticket(issue.id, "Starting sandbox (database reset, uv sync, npm ci)");
      const sandbox = await sandcastle.createSandbox({
        branch: issue.branch,
        sandbox: docker(),
        hooks,
        copyToWorktree,
      });

      try {
        // Run the implementer
        const tracked = readyById.get(issue.id)!;
        const implementLog = agentLog(iteration, issue.id, "implementer");
        ticket(issue.id, `Implementer started (transcript: ${implementLog.path})`);
        const implement = await sandbox.run({
          name: "implementer",
          logging: implementLog,
          maxIterations: 100,
          agent: sandcastle.claudeCode(MODEL),
          promptFile: "./.sandcastle/implement-prompt.md",
          promptArgs: {
            TASK_ID: issue.id,
            ISSUE_TITLE: issue.title,
            ISSUE_PATH: tracked.path,
            SPEC_PATH: tracked.specPath ?? "(no spec for this feature)",
            BRANCH: issue.branch,
          },
        });

        // Only review if the implementer produced commits
        ticket(
          issue.id,
          `Implementer finished after ${implement.iterations.length} iteration(s), ` +
            `${implement.completionSignal ? "signalled COMPLETE" : "WITHOUT signalling COMPLETE"}, ` +
            `${implement.commits.length} commit(s)`,
        );
        for (const c of describeCommits(implement.commits)) ticket(issue.id, `  commit ${c}`);

        if (implement.commits.length > 0) {
          const reviewLog = agentLog(iteration, issue.id, "reviewer");
          ticket(issue.id, `Reviewer started (transcript: ${reviewLog.path})`);
          const review = await sandbox.run({
            name: "reviewer",
            logging: reviewLog,
            maxIterations: 1,
            agent: sandcastle.claudeCode(MODEL),
            promptFile: "./.sandcastle/review-prompt.md",
            promptArgs: {
              BRANCH: issue.branch,
            },
          });

          ticket(issue.id, `Reviewer finished, ${review.commits.length} commit(s)`);
          for (const c of describeCommits(review.commits)) ticket(issue.id, `  commit ${c}`);

          // Merge commits from both runs so the merge phase sees all of them.
          // Each sandbox.run() only returns commits from its own run.
          return {
            ...review,
            commits: [...implement.commits, ...review.commits],
          };
        }

        ticket(issue.id, "No commits, so nothing to review or merge this round");
        return implement;
      } finally {
        await closeSandbox(sandbox);
      }
    }),
  );

  // Log any agents that threw (network error, sandbox crash, etc.), and
  // only pass branches that actually produced commits to the merge phase.
  // An agent that ran successfully but made no commits has nothing to merge.
  const completedIssues: typeof issues = [];
  for (const [i, issue] of issues.entries()) {
    const outcome = settled[i];
    if (outcome?.status === "rejected") {
      // Covers sandbox start-up failures as well as agent failures.
      ticket(issue.id, `FAILED: ${errorText(outcome.reason)}`);
    } else if (
      outcome?.status === "fulfilled" &&
      outcome.value.commits.length > 0
    ) {
      completedIssues.push(issue);
    }
  }

  const completedBranches = completedIssues.map((i) => i.branch);

  note(
    `Execution complete. ${completedBranches.length} branch(es) with commits: ` +
      (completedBranches.join(", ") || "none"),
  );

  if (completedBranches.length === 0) {
    // All agents ran but none made commits — nothing to merge this cycle.
    note("No commits produced. Nothing to merge.");
    continue;
  }

  // -------------------------------------------------------------------------
  // Phase 3: Merge
  //
  // One agent merges all completed branches, resolving any conflicts and
  // running tests to confirm everything works. It works on its own branch
  // (faet/merge/<run>-round-NN, forked from your current branch) in its own
  // sandbox; afterwards your branch is fast-forwarded to it here on the host.
  //
  // Why not sandcastle.run() with merge-to-head: it crashes the whole loop
  // when Windows git can't delete the worktree's Linux symlinks, whereas
  // createSandbox + closeSandbox clean those up from inside the container.
  // -------------------------------------------------------------------------
  const mergeLog = agentLog(iteration, "merger", "merger");
  const targetBranch = git("rev-parse", "--abbrev-ref", "HEAD");
  const mergeBranch = `${BRANCH_PREFIX}merge/${RUN_ID}-round-${String(iteration).padStart(2, "0")}`;
  for (const issue of completedIssues) {
    ticket(issue.id, `Merging on ${mergeBranch} (transcript: ${mergeLog.path})`);
  }
  try {
    const mergeSandbox = await sandcastle.createSandbox({
      branch: mergeBranch,
      baseBranch: targetBranch,
      sandbox: docker(),
      hooks,
      copyToWorktree,
    });
    try {
      await mergeSandbox.run({
        name: "merger",
        logging: mergeLog,
        maxIterations: 1,
        agent: sandcastle.claudeCode(MODEL),
        promptFile: "./.sandcastle/merge-prompt.md",
        promptArgs: {
          // A markdown list of branch names, one per line.
          BRANCHES: completedBranches.map((b) => `- ${b}`).join("\n"),
          // A markdown list of issue IDs and titles, one per line.
          ISSUES: completedIssues.map((i) => `- ${i.id}: ${i.title}`).join("\n"),
        },
      });
    } finally {
      await closeSandbox(mergeSandbox);
    }

    // Bring the merges onto your branch. --ff-only: if your branch moved
    // during the round, nothing is overwritten and the round is left for you.
    git("merge", "--ff-only", mergeBranch);
    git("branch", "-d", mergeBranch);
    note(`Fast-forwarded ${targetBranch} to the merge.`);
  } catch (e) {
    note(
      `Merge step failed: ${errorText(e)}. ` +
        `Its work (if any) is on ${mergeBranch}; affected tickets stay open.`,
    );
  }

  // Close (Status: done) only the issues whose branch really landed on HEAD,
  // so a merge the agent gave up on leaves its issue open for the next round.
  for (const issue of completedIssues) {
    try {
      execFileSync("git", ["merge-base", "--is-ancestor", issue.branch, "HEAD"]);
      closeIssue(readyById.get(issue.id)!);
      ticket(issue.id, "Merged and marked done");
    } catch {
      ticket(issue.id, `NOT merged (${issue.branch} isn't on HEAD); left open for the next round`);
    }
  }

  note(`Round ${iteration} finished.`);
}

note("All done.");
