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
        'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-navy-400/40',
        tone === 'danger' && 'bg-navy-800 text-status-expired hover:bg-navy-700',
        tone === 'default' && 'bg-navy-700 text-navy-50 hover:bg-navy-600',
        tone === 'primary' && 'bg-navy-600 px-4 py-2 text-sm text-navy-50 hover:bg-navy-500',
        className,
      )}
    />
  )
}
