/** Every status (NFR-04) is a dot and a word: the word in `ink-muted` carries
 * the meaning, the dot is a second signal. Only problems get a hue: `warn`
 * (needs attention) and `bad` (blocks an assignment). Each tone string ends
 * with the overrides that strip a caller's pill styles (callers merge it last
 * with `cn`). Colours live in src/index.css; tests/badgeContrast.test.ts
 * checks the word against the grounds and each dot at 3:1. */
export type BadgeTone = 'ok' | 'warn' | 'bad' | 'neutral' | 'muted'

const BASE =
  'inline-flex items-center gap-1.5 rounded-none bg-transparent px-0 py-0 font-normal text-ink-muted ' +
  'before:size-1.5 before:shrink-0 before:rounded-full before:content-[""]'

export const BADGE_TONE: Record<BadgeTone, string> = {
  ok: `${BASE} before:bg-ink-faint`,
  warn: `${BASE} before:bg-warning`,
  bad: `${BASE} before:bg-danger`,
  neutral: `${BASE} before:ring-1 before:ring-inset before:ring-ink-faint`,
  muted: `${BASE} text-ink-faint before:ring-1 before:ring-inset before:ring-ink-faint`,
}

/** The dot colour token of each tone, for the contrast test. */
export const DOT_COLOUR: Record<BadgeTone, string> = {
  ok: 'ink-faint',
  warn: 'warning',
  bad: 'danger',
  neutral: 'ink-faint',
  muted: 'ink-faint',
}
