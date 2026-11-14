// Per-run, per-ticket log files for main.mts.
//
//   .sandcastle/logs/<run-started-at>/
//     run.log                              overview of the whole run
//     planner/round-01.log                 planner agent transcript
//     merger/round-01.log                  merger agent transcript
//     <issue-id>/progress.log              short timeline for one ticket
//     <issue-id>/round-01-implementer.log  full agent transcript
//     <issue-id>/round-01-reviewer.log     full agent transcript
//
// `.sandcastle/logs/` is gitignored.

import { appendFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";

const stamp = () => new Date().toISOString().replace("T", " ").slice(0, 19);

export const RUN_DIR = join(
  ".sandcastle",
  "logs",
  new Date().toISOString().slice(0, 19).replace(/:/g, "-"),
);
mkdirSync(RUN_DIR, { recursive: true });

function append(file: string, line: string): void {
  mkdirSync(dirname(file), { recursive: true });
  appendFileSync(file, `${stamp()}  ${line}\n`);
}

const pad = (n: number) => String(n).padStart(2, "0");

/** Logs to the terminal and run.log. */
export function note(message: string): void {
  console.log(message);
  append(join(RUN_DIR, "run.log"), message);
}

/** Logs to the terminal, run.log and the ticket's progress.log. */
export function ticket(issueId: string, message: string): void {
  console.log(`  [${issueId}] ${message}`);
  append(join(RUN_DIR, "run.log"), `[${issueId}] ${message}`);
  append(join(RUN_DIR, issueId, "progress.log"), message);
}

/** Sandcastle `logging` option that writes an agent transcript to a file. */
export function agentLog(
  round: number,
  owner: string,
  agent: string,
): { type: "file"; path: string } {
  const file =
    owner === agent
      ? join(RUN_DIR, owner, `round-${pad(round)}.log`)
      : join(RUN_DIR, owner, `round-${pad(round)}-${agent}.log`);
  mkdirSync(dirname(file), { recursive: true });
  return { type: "file", path: file };
}

/** "abc1234 RALPH: subject" for each commit, best effort. */
export function describeCommits(commits: readonly { sha: string }[]): string[] {
  return commits.map(({ sha }) => {
    try {
      return execFileSync("git", ["log", "-1", "--format=%h %s", sha], {
        encoding: "utf8",
      }).trim();
    } catch {
      return sha.slice(0, 7);
    }
  });
}

export const errorText = (e: unknown) =>
  e instanceof Error ? `${e.name}: ${e.message}` : String(e);
