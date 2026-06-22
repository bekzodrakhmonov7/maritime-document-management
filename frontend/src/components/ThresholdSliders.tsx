import * as Slider from '@radix-ui/react-slider'
import { cn } from '../lib/cn'

interface ThresholdSliderProps {
  id: string
  label: string
  description: string
  value: number
  min?: number
  max?: number
  step?: number
  disabled?: boolean
  onChange: (value: number) => void
}

export function ThresholdSlider({
  id,
  label,
  description,
  value,
  min = 1,
  max = 180,
  step = 1,
  disabled = false,
  onChange,
}: ThresholdSliderProps) {
  return (
    <div className="rounded-xl border border-navy-800 bg-navy-900 p-5">
      <div className="flex items-center justify-between">
        <label
          htmlFor={id}
          className="text-sm font-semibold text-navy-100"
        >
          {label}
        </label>
        <span
          className="rounded-lg bg-navy-800 px-3 py-1 text-sm font-bold tabular-nums text-navy-50"
          aria-live="polite"
        >
          {value} days
        </span>
      </div>
      <p className="mt-1 text-xs text-navy-400">{description}</p>

      <div className="mt-4 px-1">
        <Slider.Root
          id={id}
          className={cn(
            'relative flex h-5 w-full touch-none select-none items-center',
            disabled && 'opacity-50',
          )}
          value={[value]}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          onValueChange={(vals) => {
            if (vals[0] !== undefined) {
              onChange(vals[0])
            }
          }}
          aria-valuetext={`${value} days`}
        >
          <Slider.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-navy-700">
            <Slider.Range className="absolute h-full rounded-full bg-navy-400" />
          </Slider.Track>
          <Slider.Thumb
            className={cn(
              'block h-5 w-5 rounded-full bg-navy-50 shadow-lg',
              'focus:outline-none focus:ring-2 focus:ring-navy-400/60 focus:ring-offset-2 focus:ring-offset-navy-900',
              'transition-transform hover:scale-110',
              'disabled:pointer-events-none',
            )}
            aria-label={label}
          />
        </Slider.Root>
      </div>

      <div className="mt-2 flex justify-between text-xs text-navy-500">
        <span>{min}d</span>
        <span>{max}d</span>
      </div>
    </div>
  )
}

interface ThresholdSlidersProps {
  values: { days_90: number; days_60: number; days_30: number }
  disabled?: boolean
  onChange: (key: 'days_90' | 'days_60' | 'days_30', value: number) => void
}

export function ThresholdSliders({ values, disabled, onChange }: ThresholdSlidersProps) {
  return (
    <div className="space-y-4">
      <ThresholdSlider
        id="threshold-90"
        label="Early Warning"
        description="First alert when document expires within this many days"
        value={values.days_90}
        max={180}
        disabled={disabled}
        onChange={(v) => onChange('days_90', v)}
      />
      <ThresholdSlider
        id="threshold-60"
        label="Mid Warning"
        description="Second alert escalation threshold"
        value={values.days_60}
        max={120}
        disabled={disabled}
        onChange={(v) => onChange('days_60', v)}
      />
      <ThresholdSlider
        id="threshold-30"
        label="Critical Warning"
        description="Final urgent alert before expiry"
        value={values.days_30}
        max={60}
        disabled={disabled}
        onChange={(v) => onChange('days_30', v)}
      />
    </div>
  )
}
