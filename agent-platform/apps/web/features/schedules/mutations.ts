import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type Schemas } from "@/lib/api/client";

import { scheduleKeys } from "./queries";

type ScheduleIn = Schemas["ScheduleIn"];
type ScheduleOut = Schemas["ScheduleOut"];

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: scheduleKeys.all });
    void qc.invalidateQueries({ queryKey: ["dashboard"] });
    void qc.invalidateQueries({ queryKey: ["pipelines"] });
  };
}

/** Create (no id) or replace (with id). The form shows errors inline. */
export function useSaveSchedule() {
  const invalidate = useInvalidate();
  return useMutation({
    meta: { silent: true },
    mutationFn: async ({ id, body }: { id?: string; body: ScheduleIn }) =>
      id
        ? unwrap(await api.PUT("/api/v1/schedules/{schedule_id}", { params: { path: { schedule_id: id } }, body }))
        : unwrap(await api.POST("/api/v1/schedules", { body })),
    onSuccess: invalidate,
  });
}

/** The API has no PATCH: toggling active re-sends the full schedule. */
export function toScheduleIn(s: ScheduleOut, patch: Partial<ScheduleIn> = {}): ScheduleIn {
  return {
    pipeline_id: s.pipeline_id,
    name: s.name,
    kind: s.kind,
    cron: s.cron,
    interval_seconds: s.interval_seconds,
    daily_time: s.daily_time,
    timezone: s.timezone,
    input: s.input,
    overlap_policy: s.overlap_policy,
    is_active: s.is_active,
    ...patch,
  };
}

export function useSetScheduleActive() {
  const qc = useQueryClient();
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async ({ schedule, active }: { schedule: ScheduleOut; active: boolean }) =>
      unwrap(
        await api.PUT("/api/v1/schedules/{schedule_id}", {
          params: { path: { schedule_id: schedule.id } },
          body: toScheduleIn(schedule, { is_active: active }),
        }),
      ),
    onMutate: async ({ schedule, active }) => {
      await qc.cancelQueries({ queryKey: scheduleKeys.list });
      const previous = qc.getQueryData<ScheduleOut[]>(scheduleKeys.list);
      qc.setQueryData<ScheduleOut[]>(scheduleKeys.list, (rows) => rows?.map((r) => (r.id === schedule.id ? { ...r, is_active: active } : r)));
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) qc.setQueryData(scheduleKeys.list, context.previous);
    },
    onSettled: invalidate,
  });
}

export function useDeleteSchedule() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (id: string) => unwrap(await api.DELETE("/api/v1/schedules/{schedule_id}", { params: { path: { schedule_id: id } } })),
    onSuccess: invalidate,
  });
}
