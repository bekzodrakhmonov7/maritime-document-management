import { useState, useEffect } from 'react'
import {
  Settings,
  Save,
  Loader2,
  AlertCircle,
  CheckCircle,
  RotateCcw,
  Zap,
  Mail,
} from 'lucide-react'
import { useThresholds, useTriggerScan, useUpdateThresholds } from '../hooks/useAlerts'
import { ThresholdSliders } from '../components/ThresholdSliders'
import { cn } from '../lib/cn'
import type { ThresholdConfig } from '../types'

const DEFAULT_THRESHOLDS: ThresholdConfig = {
  days_90: 90,
  days_60: 60,
  days_30: 30,
}

export function AdminConfigPage() {
  const thresholdsQuery = useThresholds()
  const updateMutation = useUpdateThresholds()
  const scanMutation = useTriggerScan()

  const [values, setValues] = useState<ThresholdConfig>(DEFAULT_THRESHOLDS)
  const [saved, setSaved] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)

  useEffect(() => {
    if (thresholdsQuery.data) {
      setValues(thresholdsQuery.data)
    }
  }, [thresholdsQuery.data])

  const serverValues = thresholdsQuery.data
  const hasChanges =
    serverValues !== undefined &&
    (values.days_90 !== serverValues.days_90 ||
      values.days_60 !== serverValues.days_60 ||
      values.days_30 !== serverValues.days_30)

  const handleChange = (key: keyof ThresholdConfig, value: number) => {
    setValues((prev) => ({ ...prev, [key]: value }))
    setSaved(false)
  }

  const handleSave = async () => {
    if (!serverValues) return

    if (values.days_90 <= values.days_60 || values.days_60 <= values.days_30) {
      setValidationError('Thresholds must be in descending order (Early > Mid > Critical).')
      return
    }
    setValidationError(null)

    const updates: Partial<ThresholdConfig> = {}
    if (values.days_90 !== serverValues.days_90) updates.days_90 = values.days_90
    if (values.days_60 !== serverValues.days_60) updates.days_60 = values.days_60
    if (values.days_30 !== serverValues.days_30) updates.days_30 = values.days_30

    if (Object.keys(updates).length === 0) return

    try {
      await updateMutation.mutateAsync(updates)
      setSaved(true)
    } catch {
      setSaved(false)
    }
  }

  const handleReset = () => {
    if (serverValues) {
      setValues(serverValues)
      setSaved(false)
    }
  }

  const isPending = updateMutation.isPending
  const isLoading = thresholdsQuery.isLoading

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Settings className="h-5 w-5 text-navy-300" aria-hidden="true" />
          <h1 className="text-xl font-bold tracking-tight text-navy-50">
            Alert Threshold Configuration
          </h1>
        </div>
        <p className="text-sm text-navy-400">
          Configure when document expiry alerts are triggered across the fleet
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center rounded-xl border border-navy-800 bg-navy-900 p-12">
          <Loader2 className="h-6 w-6 animate-spin text-navy-300" />
          <span className="ml-3 text-sm text-navy-300">Loading threshold configuration...</span>
        </div>
      )}

      {thresholdsQuery.isError && !isLoading && (
        <div
          role="alert"
          className="flex items-center gap-3 rounded-xl border border-status-expired/40 bg-status-expired-bg/10 p-6"
        >
          <AlertCircle className="h-5 w-5 shrink-0 text-status-expired" />
          <p className="text-sm text-status-expired">
            Failed to load threshold configuration. Please try again later.
          </p>
        </div>
      )}

      {!isLoading && !thresholdsQuery.isError && (
        <div className="max-w-2xl space-y-6">
          <div className="rounded-xl border border-navy-800 bg-navy-900 p-5">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-status-expiring" aria-hidden="true" />
              <div>
                <h2 className="text-sm font-semibold text-navy-100">
                  How Alert Thresholds Work
                </h2>
                <p className="mt-1 text-xs text-navy-400">
                  When a document's expiry date falls within a threshold window, an alert is
                  automatically generated. Lower thresholds indicate higher urgency. Thresholds
                  must be set in descending order (Early &gt; Mid &gt; Critical).
                </p>
              </div>
            </div>
          </div>

          <ThresholdSliders
            values={values}
            disabled={isPending}
            onChange={handleChange}
          />

          {validationError && (
            <div
              role="alert"
              className="flex items-start gap-3 rounded-lg border border-status-expired/40 bg-status-expired-bg/10 p-4"
            >
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-status-expired" />
              <p className="text-sm text-status-expired">{validationError}</p>
            </div>
          )}

          {updateMutation.isError && (
            <div
              role="alert"
              className="flex items-start gap-3 rounded-lg border border-status-expired/40 bg-status-expired-bg/10 p-4"
            >
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-status-expired" />
              <p className="text-sm text-status-expired">
                {updateMutation.error instanceof Error
                  ? updateMutation.error.message
                  : 'Failed to save threshold configuration.'}
              </p>
            </div>
          )}

          {saved && !updateMutation.isError && (
            <div
              role="status"
              className="flex items-center gap-3 rounded-lg border border-status-valid/40 bg-status-valid-bg/10 p-4"
            >
              <CheckCircle className="h-5 w-5 shrink-0 text-status-valid" />
              <p className="text-sm text-status-valid">
                Threshold configuration saved successfully.
              </p>
            </div>
          )}

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleSave}
              disabled={!hasChanges || isPending}
              className={cn(
                'inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-navy-400/40',
                hasChanges && !isPending
                  ? 'bg-navy-600 text-navy-50 hover:bg-navy-500'
                  : 'cursor-not-allowed bg-navy-800 text-navy-500',
              )}
              aria-label="Save threshold configuration"
            >
              {isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" aria-hidden="true" />
              )}
              {isPending ? 'Saving...' : 'Save Configuration'}
            </button>

            {hasChanges && !isPending && (
              <button
                type="button"
                onClick={handleReset}
                className="inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-navy-300 transition-colors hover:bg-navy-800 hover:text-navy-100 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
              >
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
                Reset
              </button>
            )}
          </div>

          <div className="rounded-xl border border-navy-800 bg-navy-900 p-5">
            <div className="flex items-start gap-3">
              <Zap className="mt-0.5 h-5 w-5 shrink-0 text-status-expiring" aria-hidden="true" />
              <div className="flex-1">
                <h2 className="text-sm font-semibold text-navy-100">Run Expiry Scan</h2>
                <p className="mt-1 text-xs text-navy-400">
                  Manually runs the same pipeline as the daily 09:00 scan: transitions document
                  statuses, generates new alerts, and emails administrators for any new threshold
                  breaches.
                </p>

                <div className="mt-4">
                  <button
                    type="button"
                    onClick={() => scanMutation.mutate()}
                    disabled={scanMutation.isPending}
                    className={cn(
                      'inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-navy-400/40',
                      !scanMutation.isPending
                        ? 'bg-navy-600 text-navy-50 hover:bg-navy-500'
                        : 'cursor-not-allowed bg-navy-800 text-navy-500',
                    )}
                    aria-label="Run expiry scan"
                  >
                    {scanMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Zap className="h-4 w-4" aria-hidden="true" />
                    )}
                    {scanMutation.isPending ? 'Scanning...' : 'Run Scan Now'}
                  </button>
                </div>

                {scanMutation.isError && (
                  <div
                    role="alert"
                    className="mt-4 flex items-start gap-3 rounded-lg border border-status-expired/40 bg-status-expired-bg/10 p-4"
                  >
                    <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-status-expired" />
                    <p className="text-sm text-status-expired">
                      {scanMutation.error instanceof Error
                        ? scanMutation.error.message
                        : 'Failed to run expiry scan.'}
                    </p>
                  </div>
                )}

                {scanMutation.isSuccess && scanMutation.data && (
                  <div
                    role="status"
                    className="mt-4 flex items-start gap-3 rounded-lg border border-status-valid/40 bg-status-valid-bg/10 p-4"
                  >
                    <CheckCircle className="mt-0.5 h-5 w-5 shrink-0 text-status-valid" />
                    <div className="text-sm text-status-valid">
                      <p>
                        Scan complete on {scanMutation.data.date}. Status changes:{' '}
                        <span className="font-semibold">{scanMutation.data.transitioned}</span>.
                        New alerts:{' '}
                        <span className="font-semibold">{scanMutation.data.alerts_generated}</span>.
                      </p>
                      <p className="mt-1 flex items-center gap-1.5">
                        <Mail className="h-3.5 w-3.5" aria-hidden="true" />
                        Emails sent:{' '}
                        <span className="font-semibold">{scanMutation.data.emails_sent}</span>.
                        Failed:{' '}
                        <span className="font-semibold">{scanMutation.data.emails_failed}</span>.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
