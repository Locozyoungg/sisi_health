import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";

interface QueueRow {
  assessment_id: string;
  pseudonym: string;
  band: string;
  age_band: string;
  consent_state: string;
  channel: string;
  requested_contact: boolean;
  created_at: string;
}

const ACTIONS = ["spoke_to", "referred", "escalated", "contacted"] as const;

/** The nurse flag queue: pseudonyms, bands, actions — NEVER raw symptom
 * narratives (non-negotiable 5; asserted by the Playwright e2e). */
export default function Queue() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["queue"],
    queryFn: () => api<QueueRow[]>("/v1/school/queue"),
    refetchInterval: 30_000,
  });

  const action = useMutation({
    mutationFn: (input: { assessment_id: string; action: string }) =>
      api("/v1/school/actions", {
        method: "POST",
        body: JSON.stringify({ ...input, note: "" }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["queue"] }),
  });

  if (isLoading) return <main>Loading…</main>;
  if (error) return <main role="alert">{String(error)}</main>;

  return (
    <main style={{ maxWidth: 900, margin: "0 auto", padding: 24 }}>
      <h1>Flag queue</h1>
      <p>School staff see severity bands and actions only.</p>
      <table>
        <thead>
          <tr>
            <th>Student</th>
            <th>Band</th>
            <th>Age band</th>
            <th>Consent</th>
            <th>Channel</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {(data ?? []).map((row) => (
            <tr key={row.assessment_id} data-testid="queue-row">
              <td>{row.pseudonym.slice(0, 8)}</td>
              <td>{row.band}</td>
              <td>{row.age_band}</td>
              <td>{row.consent_state}</td>
              <td>{row.channel}</td>
              <td>
                <select
                  defaultValue=""
                  onChange={(e) => {
                    if (e.target.value) {
                      action.mutate({ assessment_id: row.assessment_id, action: e.target.value });
                    }
                  }}
                  aria-label={`action for ${row.pseudonym.slice(0, 8)}`}
                >
                  <option value="" disabled>
                    record action
                  </option>
                  {ACTIONS.map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
              </td>
            </tr>
          ))}
          {(data ?? []).length === 0 && (
            <tr>
              <td colSpan={6}>Queue is empty.</td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}
