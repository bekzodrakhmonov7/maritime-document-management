import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { retryUnlessClientError } from '../lib/retry'
import type {
  Assignment,
  AssignmentCreate,
  AssignmentEdit,
  Readiness,
  ResponsibleOfficer,
} from '../types'

/** Every Assignment of one seafarer, finished and cancelled ones included. */
export function useSeafarerAssignments(seafarerId: number) {
  return useQuery({
    queryKey: ['assignments', 'seafarer', seafarerId],
    queryFn: () => apiFetch<Assignment[]>(`/api/seafarers/${seafarerId}/assignments`),
    enabled: Number.isInteger(seafarerId),
  })
}

/** A vessel's crew under way and upcoming. 404 for a crewing officer when
 * the vessel is outside their Scope; not retried, as each try is recorded. */
export function useVesselCrew(vesselId: number) {
  return useQuery({
    queryKey: ['assignments', 'vessel', vesselId],
    queryFn: () => apiFetch<Assignment[]>(`/api/vessels/${vesselId}/crew`),
    enabled: Number.isInteger(vesselId),
    retry: (failureCount, error: Error) => retryUnlessClientError(failureCount, error),
  })
}

/** The advice-only readiness view of an upcoming or under-way Assignment. */
export function useReadiness(assignmentId: number) {
  return useQuery({
    queryKey: ['readiness', assignmentId],
    queryFn: () => apiFetch<Readiness>(`/api/assignments/${assignmentId}/readiness`),
    enabled: Number.isInteger(assignmentId),
  })
}

export type AssignmentAction =
  | { kind: 'create'; body: AssignmentCreate }
  | { kind: 'edit'; id: number; body: AssignmentEdit }
  | { kind: 'cancel'; id: number; reason: string }

function request(action: AssignmentAction) {
  switch (action.kind) {
    case 'create':
      return apiFetch<Assignment>('/api/assignments', {
        method: 'POST',
        body: JSON.stringify(action.body),
      })
    case 'edit':
      return apiFetch<Assignment>(`/api/assignments/${action.id}`, {
        method: 'PUT',
        body: JSON.stringify(action.body),
      })
    case 'cancel':
      return apiFetch<Assignment>(`/api/assignments/${action.id}/cancel`, {
        method: 'POST',
        body: JSON.stringify({ reason: action.reason }),
      })
  }
}

/** Plan, edit or cancel. Assignments move seafarers in and out of Scope and
 * change their Current Vessel, so seafarer lists are refreshed too. */
export function useAssignmentAction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: request,
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['assignments'] }),
        queryClient.invalidateQueries({ queryKey: ['seafarers'] }),
        queryClient.invalidateQueries({ queryKey: ['readiness'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      ]),
  })
}

const officersPath = (vesselId: number) => `/api/vessels/${vesselId}/responsible-officers`

export function useResponsibleOfficers(vesselId: number) {
  return useQuery({
    queryKey: ['responsible-officers', vesselId],
    queryFn: () => apiFetch<ResponsibleOfficer[]>(officersPath(vesselId)),
    enabled: Number.isInteger(vesselId),
  })
}

/** Administrators link or unlink a crewing officer. */
export function useResponsibleOfficerAction(vesselId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ kind, accountId }: { kind: 'add' | 'remove'; accountId: string }) =>
      kind === 'add'
        ? apiFetch(officersPath(vesselId), {
            method: 'POST',
            body: JSON.stringify({ account_id: accountId }),
          })
        : apiFetch(`${officersPath(vesselId)}/${accountId}`, { method: 'DELETE' }),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['responsible-officers', vesselId] }),
        queryClient.invalidateQueries({ queryKey: ['vessels'] }),
      ]),
  })
}
