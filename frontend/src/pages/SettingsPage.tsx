import { useMemo, useState, type FormEvent } from 'react'
import { Loader2, Lock, Play, Plus, RotateCw, X } from 'lucide-react'
import { useSaveSettings, useSettings } from '../hooks/useSettings'
import { useRunDailyCheck } from '../hooks/useAlerts'
import { ApiError } from '../lib/api'
import type { LastCleanup, Settings } from '../types'
import { ActionButton } from '../components/ActionButton'
import { ErrorNote } from '../components/ErrorNote'
import { FIELD_CLASS, LABEL_CLASS } from '../components/FormDialog'
import { FILE_SIZE_CEILING_MB } from '../lib/fileSize'

const MAX_ALERT_STEPS = 6

/** Every quarter hour of the day as "HH:MM". */
const CHECK_TIMES = Array.from({ length: 96 }, (_, i) => {
  const hh = String(Math.floor(i / 4)).padStart(2, '0')
  const mm = String((i % 4) * 15).padStart(2, '0')
  return `${hh}:${mm}`
})

function timeZones(current: string): string[] {
  const zones = new Set(Intl.supportedValuesOf('timeZone'))
  zones.add('UTC')
  zones.add(current)
  return [...zones].sort()
}

const NUMBER_FIELDS = [
  {
    key: 'planning_horizon_days',
    label: 'Planning Horizon',
    unit: 'days',
    min: 7,
    max: 365,
    hint: 'How far ahead an Assignment counts as starting soon.',
  },
  { key: 'max_file_size_mb', label: 'Maximum file size', unit: 'MB', min: 1, max: FILE_SIZE_CEILING_MB, hint: null },
  { key: 'max_pdf_pages', label: 'Maximum PDF pages', unit: 'pages', min: 1, max: 500, hint: null },
] as const

const RETENTION_FIELDS = [
  {
    key: 'retention_replaced_version_years',
    label: 'Replaced Versions',
    hint: 'Counted from the Review that accepted a newer Version or rejected this one.',
  },
  {
    key: 'retention_inactive_seafarer_years',
    label: 'Inactive seafarers',
    hint: 'The whole record, counted from the day the seafarer became Inactive.',
  },
  {
    key: 'retention_audit_record_years',
    label: 'Audit Records',
    hint: 'Counted from when the record was written.',
  },
] as const

const MAX_RETENTION_YEARS = 10

type NumberKey =
  | (typeof NUMBER_FIELDS)[number]['key']
  | (typeof RETENTION_FIELDS)[number]['key']

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

/** System-wide settings (administrators only). */
export function SettingsPage() {
  const { data, isLoading, error, refetch, isFetching } = useSettings()
  const save = useSaveSettings()

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-navy-50">Settings</h2>
        <p className="mt-1 text-sm text-navy-400">
          Changes apply from the next request or the next daily check. No restart is needed.
        </p>
      </div>

      {isLoading && <p className="text-navy-400">Loading…</p>}
      {error && <ErrorNote message={error.message} />}
      {data && (
        // A new version (after a save or a reload) starts the form afresh.
        <SettingsForm
          key={data.version}
          settings={data}
          save={save}
          reloading={isFetching}
          onReload={() => {
            save.reset()
            void refetch()
          }}
        />
      )}

      {data && <LastCleanupPanel cleanup={data.last_cleanup} timeZone={data.time_zone} />}

      <DailyCheckPanel />
    </div>
  )
}

/** What the scheduled daily check's last retention clean-up removed. */
function LastCleanupPanel({ cleanup, timeZone }: { cleanup: LastCleanup | null; timeZone: string }) {
  return (
    <section
      aria-labelledby="last-cleanup-heading"
      className="space-y-2 rounded-xl border border-navy-800 bg-navy-900 p-6"
    >
      <h3 id="last-cleanup-heading" className="text-sm font-semibold text-navy-50">
        Last retention clean-up
      </h3>
      {cleanup === null ? (
        <p className="text-sm text-navy-400">
          No clean-up has run yet. It runs as the last step of the scheduled daily check.
        </p>
      ) : (
        <p className="text-sm text-navy-200">
          {new Date(cleanup.finished_at).toLocaleString(undefined, {
            timeZone,
            dateStyle: 'medium',
            timeStyle: 'short',
          })}
          : removed {plural(cleanup.versions, 'Replaced Version')},{' '}
          {plural(cleanup.seafarers, 'Inactive seafarer')} and{' '}
          {plural(cleanup.audit_records, 'Audit Record')}.
        </p>
      )}
    </section>
  )
}

/** Run the daily check now. It doesn't count as the day's scheduled run, and
 * it is recorded in the Audit Log. */
function DailyCheckPanel() {
  const run = useRunDailyCheck()
  const result = run.data

  return (
    <section
      aria-labelledby="daily-check-heading"
      className="space-y-3 rounded-xl border border-navy-800 bg-navy-900 p-6"
    >
      <div>
        <h3 id="daily-check-heading" className="text-sm font-semibold text-navy-50">
          Daily check
        </h3>
        <p className="mt-1 text-xs text-navy-400">
          Runs once a day at the check time. Running it now raises any alerts due, sends the
          digests and retries failed e-mails; it doesn’t replace today’s scheduled run and never
          removes anything (retention runs only in the scheduled check).
        </p>
      </div>
      {run.error && <ErrorNote message={run.error.message} />}
      {result && (
        <p className="text-sm text-navy-200" role="status">
          Raised {result.raised} alert{result.raised === 1 ? '' : 's'}, sent {result.sent} digest
          {result.sent === 1 ? '' : 's'}
          {result.failed > 0 && `, ${result.failed} failed (retried on the next run)`}.
        </p>
      )}
      <ActionButton tone="primary" onClick={() => run.mutate()} disabled={run.isPending}>
        {run.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
        Run now
      </ActionButton>
    </section>
  )
}

interface SettingsFormProps {
  settings: Settings
  save: ReturnType<typeof useSaveSettings>
  reloading: boolean
  onReload: () => void
}

function SettingsForm({ settings, save, reloading, onReload }: SettingsFormProps) {
  const [steps, setSteps] = useState<number[]>(settings.alert_steps)
  const [numbers, setNumbers] = useState<Record<NumberKey, string>>({
    planning_horizon_days: String(settings.planning_horizon_days),
    max_file_size_mb: String(settings.max_file_size_mb),
    max_pdf_pages: String(settings.max_pdf_pages),
    retention_replaced_version_years: String(settings.retention_replaced_version_years),
    retention_inactive_seafarer_years: String(settings.retention_inactive_seafarer_years),
    retention_audit_record_years: String(settings.retention_audit_record_years),
  })
  const [timeZone, setTimeZone] = useState(settings.time_zone)
  const [checkTime, setCheckTime] = useState(settings.daily_check_time)
  const zones = useMemo(() => timeZones(settings.time_zone), [settings.time_zone])

  const stale = save.error instanceof ApiError && save.error.status === 409

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate({
      alert_steps: steps,
      planning_horizon_days: Number(numbers.planning_horizon_days),
      max_file_size_mb: Number(numbers.max_file_size_mb),
      max_pdf_pages: Number(numbers.max_pdf_pages),
      time_zone: timeZone,
      daily_check_time: checkTime,
      retention_replaced_version_years: Number(numbers.retention_replaced_version_years),
      retention_inactive_seafarer_years: Number(numbers.retention_inactive_seafarer_years),
      retention_audit_record_years: Number(numbers.retention_audit_record_years),
      version: settings.version,
    })
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-6 rounded-xl border border-navy-800 bg-navy-900 p-6"
    >
      <AlertStepsEditor steps={steps} onChange={setSteps} />

      <div className="grid gap-4 sm:grid-cols-3">
        {NUMBER_FIELDS.map((field) => (
          <div key={field.key}>
            <label htmlFor={field.key} className={LABEL_CLASS}>
              {field.label} ({field.unit})
            </label>
            <input
              id={field.key}
              type="number"
              required
              step={1}
              min={field.min}
              max={field.max}
              value={numbers[field.key]}
              onChange={(e) => setNumbers({ ...numbers, [field.key]: e.target.value })}
              className={FIELD_CLASS}
            />
            <p className="mt-1 text-xs text-navy-400">
              {field.min}–{field.max} {field.unit}. {field.hint}
            </p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="time_zone" className={LABEL_CLASS}>
            Company time zone
          </label>
          <select
            id="time_zone"
            value={timeZone}
            onChange={(e) => setTimeZone(e.target.value)}
            className={FIELD_CLASS}
          >
            {zones.map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-navy-400">
            Decides “today” for statuses and alerts, and how times are shown.
          </p>
        </div>
        <div>
          <label htmlFor="daily_check_time" className={LABEL_CLASS}>
            Daily check time
          </label>
          <select
            id="daily_check_time"
            value={checkTime}
            onChange={(e) => setCheckTime(e.target.value)}
            className={FIELD_CLASS}
          >
            {CHECK_TIMES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-navy-400">In the company time zone, every 15 minutes.</p>
        </div>
      </div>

      <fieldset>
        <legend className={LABEL_CLASS}>Retention Periods (whole years)</legend>
        <p className="mb-3 text-xs text-navy-400">
          Removed automatically when the period ends, as the last step of the scheduled daily
          check. Audit Records about a removed seafarer are kept.
        </p>
        <div className="grid gap-4 sm:grid-cols-3">
          {RETENTION_FIELDS.map((field) => (
            <div key={field.key}>
              <label htmlFor={field.key} className={LABEL_CLASS}>
                {field.label} (years)
              </label>
              <input
                id={field.key}
                type="number"
                required
                step={1}
                min={1}
                max={MAX_RETENTION_YEARS}
                value={numbers[field.key]}
                onChange={(e) => setNumbers({ ...numbers, [field.key]: e.target.value })}
                className={FIELD_CLASS}
              />
              <p className="mt-1 text-xs text-navy-400">
                1–{MAX_RETENTION_YEARS} years. {field.hint}
              </p>
            </div>
          ))}
        </div>
      </fieldset>

      {save.error && (
        <div className="space-y-2">
          <ErrorNote message={save.error.message} />
          {stale && (
            <ActionButton onClick={onReload} disabled={reloading}>
              <RotateCw className="h-4 w-4" />
              Reload settings
            </ActionButton>
          )}
        </div>
      )}
      {save.isSuccess && <p className="text-sm text-status-valid">Settings saved.</p>}

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={save.isPending || stale}
          className="flex items-center gap-2 rounded-lg bg-navy-600 px-4 py-2 text-sm font-medium text-navy-50 hover:bg-navy-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {save.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          Save settings
        </button>
      </div>
    </form>
  )
}

/** 1–6 distinct whole days before expiry; 0 (the expiry day) can't be removed. */
function AlertStepsEditor({
  steps,
  onChange,
}: {
  steps: number[]
  onChange: (steps: number[]) => void
}) {
  const [draft, setDraft] = useState('')
  const value = Number(draft)
  const canAdd =
    draft.trim() !== '' &&
    Number.isInteger(value) &&
    value > 0 &&
    !steps.includes(value) &&
    steps.length < MAX_ALERT_STEPS

  const add = () => {
    if (!canAdd) return
    onChange([...steps, value].sort((a, b) => b - a))
    setDraft('')
  }

  return (
    <fieldset>
      <legend className={LABEL_CLASS}>Alert steps (days before expiry)</legend>
      <ul className="flex flex-wrap gap-2" aria-label="Alert steps">
        {steps.map((step) => (
          <li
            key={step}
            className="flex items-center gap-1.5 rounded-full bg-navy-800 px-3 py-1 text-sm text-navy-50"
          >
            {step === 0 ? (
              <>
                <Lock className="h-3.5 w-3.5 text-navy-400" aria-hidden="true" />
                0 (expiry day)
              </>
            ) : (
              <>
                {step}
                <button
                  type="button"
                  onClick={() => onChange(steps.filter((s) => s !== step))}
                  className="rounded-full p-0.5 text-navy-400 hover:text-navy-100"
                  aria-label={`Remove ${step} days`}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </>
            )}
          </li>
        ))}
      </ul>
      <div className="mt-3 flex items-center gap-2">
        <label htmlFor="new-alert-step" className="sr-only">
          New alert step in days
        </label>
        <input
          id="new-alert-step"
          type="number"
          min={1}
          step={1}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              add()
            }
          }}
          disabled={steps.length >= MAX_ALERT_STEPS}
          className={`${FIELD_CLASS} max-w-32`}
          placeholder="days"
        />
        <ActionButton onClick={add} disabled={!canAdd}>
          <Plus className="h-4 w-4" />
          Add step
        </ActionButton>
      </div>
      <p className="mt-1 text-xs text-navy-400">
        Up to {MAX_ALERT_STEPS} steps, all different. Only the most urgent step reached is sent.
      </p>
    </fieldset>
  )
}
