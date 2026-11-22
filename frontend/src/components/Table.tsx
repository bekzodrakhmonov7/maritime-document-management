import type { ReactNode } from 'react'
import { cn } from '../lib/cn'

export type Column = ReactNode | { label: ReactNode; className: string }

function isLabelled(column: Column): column is { label: ReactNode; className: string } {
  return typeof column === 'object' && column !== null && 'label' in column
}

/** A bordered data table: header row, a "Loading…" row, an empty-message row
 * (both spanning every column), then the caller's rows. */
export function Table({
  head,
  loading = false,
  empty,
  className,
  children,
}: {
  head: Column[]
  loading?: boolean
  /** Shown as the only row when set, e.g. `rows?.length === 0 ? 'None yet.' : null`. */
  empty?: ReactNode
  className?: string
  children?: ReactNode
}) {
  const messageRow = (message: ReactNode) => (
    <tr>
      <td colSpan={head.length} className="px-4 py-6 text-center text-ink-faint">
        {message}
      </td>
    </tr>
  )
  return (
    <div className={cn('overflow-x-auto rounded-md border border-line bg-canvas', className)}>
      <table className="w-full text-left text-sm">
        <thead className="border-b border-line bg-surface text-xs text-ink-faint">
          <tr>
            {head.map((column, i) =>
              isLabelled(column) ? (
                <th key={i} scope="col" className={`px-4 py-3 ${column.className}`}>
                  {column.label}
                </th>
              ) : (
                <th key={i} scope="col" className="px-4 py-3">
                  {column}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {loading && messageRow('Loading…')}
          {empty && messageRow(empty)}
          {children}
        </tbody>
      </table>
    </div>
  )
}
