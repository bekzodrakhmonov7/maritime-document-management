import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from '@tanstack/react-table'
import {
  ChevronUp,
  ChevronDown,
  ArrowUpDown,
  Eye,
  Loader2,
  AlertCircle,
  Users,
} from 'lucide-react'
import { useSeafarers } from '../hooks/useSeafarers'
import { useDocuments } from '../hooks/useDocuments'
import { StatusBadge } from './StatusBadge'
import { getDocTypeName } from '../lib/docTypes'
import { cn } from '../lib/cn'
import type { DocumentStatus, SeafarerQueryParams } from '../types'

interface CrewTableRow {
  seafarer_id: number
  name: string
  rank: string
  vessel_name: string
  doc_type_name: string
  expiry_date: string | null
  status: DocumentStatus | null
}

const columnHelper = createColumnHelper<CrewTableRow>()

const STATUS_URGENCY: Record<DocumentStatus, number> = {
  expired: 5,
  expiring_soon: 4,
  pending: 3,
  rejected: 2,
  verified: 1,
  valid: 0,
}

interface CrewTableProps {
  params?: SeafarerQueryParams
}

export function CrewTable({ params }: CrewTableProps) {
  const [sorting, setSorting] = useState<SortingState>([])

  const seafarersQuery = useSeafarers(params)
  const documentsQuery = useDocuments()

  const data = useMemo<CrewTableRow[]>(() => {
    const seafarers = seafarersQuery.data ?? []
    const documents = documentsQuery.data ?? []

    const docsBySeafarer = new Map<number, typeof documents>()
    for (const doc of documents) {
      const existing = docsBySeafarer.get(doc.seafarer_id)
      if (existing) {
        existing.push(doc)
      } else {
        docsBySeafarer.set(doc.seafarer_id, [doc])
      }
    }

    return seafarers.map((s) => {
      const seafarerDocs = docsBySeafarer.get(s.seafarer_id) ?? []
      const mostUrgent = seafarerDocs.length
        ? seafarerDocs.reduce((prev, curr) =>
            STATUS_URGENCY[curr.status] > STATUS_URGENCY[prev.status]
              ? curr
              : prev,
          )
        : null

      return {
        seafarer_id: s.seafarer_id,
        name: `${s.first_name} ${s.last_name}`,
        rank: s.rank,
        vessel_name: s.vessel_name,
        doc_type_name: mostUrgent
          ? getDocTypeName(mostUrgent.doc_type_id)
          : 'No documents',
        expiry_date: mostUrgent?.expiry_date ?? null,
        status: mostUrgent?.status ?? null,
      }
    })
  }, [seafarersQuery.data, documentsQuery.data])

  const columns = useMemo(
    () => [
      columnHelper.accessor('name', {
        header: 'Name',
        cell: (info) => (
          <span className="font-medium text-navy-50">{info.getValue()}</span>
        ),
      }),
      columnHelper.accessor('rank', {
        header: 'Rank',
        cell: (info) => (
          <span className="text-navy-200">{info.getValue()}</span>
        ),
      }),
      columnHelper.accessor('vessel_name', {
        header: 'Vessel',
        cell: (info) => (
          <span className="text-navy-200">{info.getValue()}</span>
        ),
      }),
      columnHelper.accessor('doc_type_name', {
        header: 'Document Type',
        cell: (info) => (
          <span className="text-navy-200">{info.getValue()}</span>
        ),
      }),
      columnHelper.accessor('expiry_date', {
        header: 'Expiry Date',
        cell: (info) => {
          const value = info.getValue()
          if (!value) return <span className="text-navy-500">—</span>
          const formatted = new Date(value).toLocaleDateString('en-GB', {
            day: '2-digit',
            month: 'short',
            year: 'numeric',
          })
          return <span className="text-navy-200">{formatted}</span>
        },
      }),
      columnHelper.accessor('status', {
        header: 'Status',
        enableSorting: true,
        sortingFn: (rowA, rowB) => {
          const a = rowA.original.status
            ? STATUS_URGENCY[rowA.original.status]
            : -1
          const b = rowB.original.status
            ? STATUS_URGENCY[rowB.original.status]
            : -1
          return a - b
        },
        cell: (info) => {
          const status = info.getValue()
          if (!status) return <span className="text-navy-500">—</span>
          return <StatusBadge status={status} />
        },
      }),
      columnHelper.display({
        id: 'actions',
        header: 'Actions',
        cell: (info) => (
          <Link
            to="/documents"
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-navy-300 transition-colors hover:bg-navy-700 hover:text-navy-100 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
            aria-label={`View documents for ${info.row.original.name}`}
          >
            <Eye className="h-3.5 w-3.5" aria-hidden="true" />
            View
          </Link>
        ),
      }),
    ],
    [],
  )

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  const isLoading = seafarersQuery.isLoading || documentsQuery.isLoading
  const isError = seafarersQuery.isError || documentsQuery.isError

  if (isLoading) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-navy-800 bg-navy-900 p-12">
        <Loader2 className="h-6 w-6 animate-spin text-navy-300" />
        <span className="ml-3 text-sm text-navy-300">Loading crew data...</span>
      </div>
    )
  }

  if (isError) {
    return (
      <div
        role="alert"
        className="flex items-center gap-3 rounded-xl border border-status-expired/40 bg-status-expired-bg/10 p-6"
      >
        <AlertCircle className="h-5 w-5 shrink-0 text-status-expired" />
        <p className="text-sm text-status-expired">
          Failed to load crew data. Please try again later.
        </p>
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-navy-800 bg-navy-900 p-12">
        <Users className="mb-3 h-8 w-8 text-navy-500" />
        <p className="text-sm text-navy-400">No seafarers found.</p>
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-xl border border-navy-800 bg-navy-900">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-navy-800 bg-navy-800">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const isSortable = header.column.getCanSort()
                  const sorted = header.column.getIsSorted()
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      className={cn(
                        'px-4 py-3 font-semibold text-navy-200 whitespace-nowrap',
                        isSortable && 'cursor-pointer select-none',
                      )}
                      onClick={header.column.getToggleSortingHandler()}
                      onKeyDown={(e) => {
                        if (isSortable && e.key === 'Enter') {
                          header.column.toggleSorting()
                        }
                      }}
                      tabIndex={isSortable ? 0 : undefined}
                      role={isSortable ? 'button' : undefined}
                      aria-label={
                        isSortable
                          ? `Sort by ${typeof header.column.columnDef.header === 'string' ? header.column.columnDef.header : header.id}`
                          : undefined
                      }
                    >
                      <div className="flex items-center gap-1.5">
                        {flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                        {isSortable && (
                          <span className="text-navy-400" aria-hidden="true">
                            {sorted === 'asc' ? (
                              <ChevronUp className="h-3.5 w-3.5" />
                            ) : sorted === 'desc' ? (
                              <ChevronDown className="h-3.5 w-3.5" />
                            ) : (
                              <ArrowUpDown className="h-3 w-3" />
                            )}
                          </span>
                        )}
                      </div>
                    </th>
                  )
                })}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-navy-800">
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className="transition-colors hover:bg-navy-800/50"
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-4 py-3 whitespace-nowrap">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

