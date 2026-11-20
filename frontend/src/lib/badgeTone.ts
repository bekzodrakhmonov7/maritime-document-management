/** Colours for every status badge (NFR-04). Each tone is a solid background
 * with light text, so its contrast does not depend on the surface underneath
 * and stays at least 4.5:1 in colour and in greyscale. Values live in
 * src/index.css (`--color-badge-*`); tests/badgeContrast.test.ts checks them.
 * The hue carries meaning only alongside the label (and icon), never alone. */
export type BadgeTone = 'ok' | 'warn' | 'bad' | 'neutral' | 'muted'

export const BADGE_TONE: Record<BadgeTone, string> = {
  ok: 'bg-badge-ok-bg text-badge-ok',
  warn: 'bg-badge-warn-bg text-badge-warn',
  bad: 'bg-badge-bad-bg text-badge-bad',
  neutral: 'bg-badge-neutral-bg text-badge-neutral',
  muted: 'bg-badge-muted-bg text-badge-muted',
}
