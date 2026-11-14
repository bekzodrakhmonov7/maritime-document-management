import { AlertCircle } from 'lucide-react'

export function ErrorNote({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-lg border border-status-expired/40 bg-status-expired-bg/10 p-3"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-status-expired" />
      <p className="text-sm text-status-expired">{message}</p>
    </div>
  )
}
