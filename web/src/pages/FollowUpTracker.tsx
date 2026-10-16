import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";

interface TrackerRow {
  id: string;
  pseudonym: string;
  facility_id: string | null;
  status: string;
  consent_to_share: boolean;
  due_at: string;
  lost_to_follow_up: boolean;
  updated_at: string;
}

interface Aggregates {
  enough_data: boolean;
  message: string | null;
  cells: Record<string, number | null>;
}

/** Cervical screening follow-up: status and the loss-to-follow-up flag only —
 * no results detail exists in the schema (spec 5.4.1). Aggregates render
 * through the shared k-anonymity module: suppressed cells show a dash, and
 * below threshold the page says "Not enough data yet" — never a zero. */
const TRANSITIONS: Record<string, string[]> = {
  referred: ["screened"],
  screened: ["result_received"],
  result_received: ["further_assessment"],
  further_assessment: ["treatment"],
  treatment: ["follow_up"],
  follow_up: ["completed"],
  completed: [],
};

export default function FollowUpTracker() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, error: loadError } = useQuery({
    queryKey: ["trackers"],
    queryFn: () => api<TrackerRow[]>("/v1/corridor/tracking"),
    refetchInterval: 30_000,
  });

  const {
    data: aggregates,
    isLoading: aggregatesLoading,
    error: aggregatesError,
  } = useQuery({
    queryKey: ["tracking-aggregates"],
    queryFn: () => api<Aggregates>("/v1/corridor/tracking/aggregates"),
  });

  const transition = useMutation({
    mutationFn: (input: { id: string; to_status: string }) =>
      api(`/v1/corridor/tracking/${input.id}/transition`, {
        method: "POST",
        body: JSON.stringify({ to_status: input.to_status }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trackers"] });
      queryClient.invalidateQueries({ queryKey: ["tracking-aggregates"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "transition failed"),
  });

  if (isLoading) {
    return (
      <main className="page">
        <p className="muted">Loading…</p>
      </main>
    );
  }
  if (loadError) {
    return (
      <main className="page" role="alert">
        <p className="alert alert-danger">{String(loadError)}</p>
      </main>
    );
  }

  return (
    <main className="page">
      <header className="page-head">
        <p className="eyebrow">Specialist corridor</p>
        <h1 className="page-title">Follow-up tracker</h1>
        <p className="page-sub muted">Screening follow-up status only — never results detail.</p>
      </header>
      {error && (
        <p className="alert alert-danger" role="alert">
          {error}
        </p>
      )}

      <div className="card table-card">
        <div className="table-scroll">
          <table className="table" data-testid="tracking-list">
            <thead>
              <tr>
                <th>Client</th>
                <th>Facility</th>
                <th>Status</th>
                <th>Due</th>
                <th>Loss to follow-up</th>
                <th>Sharing</th>
                <th>Move to</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((row) => {
                const allowed = TRANSITIONS[row.status] ?? [];
                return (
                  <tr key={row.id} data-testid="tracking-row">
                    <td className="cell-id">{row.pseudonym.slice(0, 8)}</td>
                    <td className="cell-id">{row.facility_id ? row.facility_id.slice(0, 8) : "—"}</td>
                    <td data-testid="tracking-status">
                      <span className="badge badge-neutral">{row.status}</span>
                    </td>
                    <td className="muted">{row.due_at}</td>
                    <td data-testid="lost-flag">{row.lost_to_follow_up ? "yes" : "no"}</td>
                    <td className="muted">{row.consent_to_share ? "consented" : "not consented"}</td>
                    <td>
                      <select
                        key={row.status}
                        className="input input-compact"
                        data-testid="tracking-transition"
                        defaultValue=""
                        disabled={allowed.length === 0}
                        aria-label={`transition for ${row.pseudonym.slice(0, 8)}`}
                        onChange={(e) => {
                          if (e.target.value) {
                            setError(null);
                            transition.mutate({ id: row.id, to_status: e.target.value });
                          }
                        }}
                      >
                        <option value="" disabled>
                          {allowed.length === 0 ? "completed" : "select status"}
                        </option>
                        {allowed.map((status) => (
                          <option key={status} value={status}>
                            {status}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                );
              })}
              {(data ?? []).length === 0 && (
                <tr>
                  <td colSpan={7} className="empty">
                    No trackers open.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2 className="card-title">Aggregates</h2>
        {aggregatesLoading && <p className="muted">Loading…</p>}
        {!aggregatesLoading && aggregatesError && (
          <p className="alert alert-info" data-testid="aggregates-unavailable">
            Aggregates are not available for your role.
          </p>
        )}
        {!aggregatesLoading && !aggregatesError && (!aggregates || !aggregates.enough_data) && (
          <p className="notice" data-testid="not-enough">
            Not enough data yet
          </p>
        )}
        {!aggregatesLoading && !aggregatesError && aggregates && aggregates.enough_data && (
          <div className="table-scroll">
            <table className="table" data-testid="tracking-aggregates">
              <tbody>
                {Object.entries(aggregates.cells).map(([key, value]) => (
                  <tr key={key}>
                    <td>{key}</td>
                    <td>{value === null ? "—" : String(value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}
