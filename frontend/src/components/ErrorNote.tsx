import { AlertCircle } from 'lucide-react'

export function ErrorNote({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
      <p className="text-sm text-danger">{message}</p>
    </div>
  )
}
