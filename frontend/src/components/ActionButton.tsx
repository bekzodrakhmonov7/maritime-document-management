import type { ButtonHTMLAttributes } from 'react'
import { cn } from '../lib/cn'

interface ActionButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  tone?: 'default' | 'danger' | 'primary'
}

/** The small buttons in table rows and page headers. */
export function ActionButton({ tone = 'default', className, ...props }: ActionButtonProps) {
  return (
    <button
      type="button"
      {...props}
      className={cn(
        'inline-flex h-8 shrink-0 items-center whitespace-nowrap gap-1.5 rounded-md border px-3 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-40',
        tone === 'danger' && 'border-line-strong bg-canvas text-danger hover:bg-surface-active',
        tone === 'default' && 'border-line-strong bg-canvas text-ink hover:bg-surface-active',
        tone === 'primary' && 'border-transparent bg-accent text-on-accent hover:bg-accent-hover',
        className,
      )}
    />
  )
}
