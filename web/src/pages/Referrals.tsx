import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, getToken } from "../api";

interface ReferralRow {
  id: string;
  user_id: string;
  status: string;
  sections: string[];
  approved_sections: string[] | null;
  created_at: string;
}

/** Referral letters: drafted by staff, sent only AFTER the patient approves the
 * sections she chose, and revocable by her at any time (spec 5.4). The PDF is
 * rendered from the approved sections only — the API refuses otherwise. */
export default function Referrals() {
  const queryClient = useQueryClient();
  const [requestId, setRequestId] = useState("");
  const [facilityId, setFacilityId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, error: loadError } = useQuery({
    queryKey: ["referrals"],
    queryFn: () => api<ReferralRow[]>("/v1/corridor/referrals"),
    refetchInterval: 30_000,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["referrals"] });

  const createReferral = useMutation({
    mutationFn: () =>
      api<{ id: string; status: string; sections: string[] }>("/v1/corridor/referrals", {
        method: "POST",
        body: JSON.stringify({
          request_id: requestId.trim(),
          facility_id: facilityId.trim() === "" ? null : facilityId.trim(),
        }),
      }),
    onSuccess: refresh,
    onError: (err) => setError(err instanceof Error ? err.message : "could not draft referral"),
  });

  const sendReferral = useMutation({
    mutationFn: (id: string) =>
      api(`/v1/corridor/referrals/${id}/send`, { method: "POST" }),
    onSuccess: refresh,
    onError: (err) => setError(err instanceof Error ? err.message : "could not send referral"),
  });

  /** The PDF endpoint needs the Bearer token, so it cannot be a plain link. */
  async function downloadPdf(id: string): Promise<void> {
    setError(null);
    const token = getToken();
    const resp = await fetch(`/v1/corridor/referrals/${id}/pdf`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!resp.ok) {
      setError("the referral letter is not approved by the patient yet");
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `referral-${id.slice(0, 8)}.pdf`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (isLoading) return <main>Loading…</main>;
  if (loadError) return <main role="alert">{String(loadError)}</main>;

  return (
    <main style={{ maxWidth: 1100, margin: "0 auto", padding: 24 }}>
      <h1>Referrals</h1>
      <p>Letters are shared only in the sections the patient approved.</p>
      {error && <p role="alert">{error}</p>}

      <form
        style={{ display: "grid", gap: 12, maxWidth: 420, marginBottom: 24 }}
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          createReferral.mutate();
        }}
      >
        <label>
          Consult request id
          <input
            data-testid="referral-request-id"
            value={requestId}
            onChange={(e) => setRequestId(e.target.value)}
            placeholder="request uuid"
          />
        </label>
        <label>
          Facility id (optional)
          <input
            data-testid="referral-facility-id"
            value={facilityId}
            onChange={(e) => setFacilityId(e.target.value)}
            placeholder="facility uuid"
          />
        </label>
        <button type="submit" data-testid="referral-create-btn" disabled={createReferral.isPending}>
          Draft referral
        </button>
      </form>

      <table data-testid="referral-list">
        <thead>
          <tr>
            <th>Referral</th>
            <th>Patient</th>
            <th>Status</th>
            <th>Sections</th>
            <th>Approved</th>
            <th>Letter</th>
          </tr>
        </thead>
        <tbody>
          {(data ?? []).map((row) => (
            <tr key={row.id} data-testid="referral-row">
              <td>{row.id.slice(0, 8)}</td>
              <td>{row.user_id.slice(0, 8)}</td>
              <td>{row.status}</td>
              <td>{row.sections.join(", ")}</td>
              <td>
                {row.approved_sections && row.approved_sections.length > 0
                  ? row.approved_sections.join(", ")
                  : "—"}
              </td>
              <td style={{ display: "flex", gap: 8 }}>
                {row.status === "approved" && (
                  <button
                    type="button"
                    data-testid="referral-send-btn"
                    disabled={sendReferral.isPending}
                    onClick={() => {
                      setError(null);
                      sendReferral.mutate(row.id);
                    }}
                  >
                    Send
                  </button>
                )}
                <button
                  type="button"
                  data-testid="referral-pdf-btn"
                  onClick={() => {
                    void downloadPdf(row.id);
                  }}
                >
                  PDF
                </button>
              </td>
            </tr>
          ))}
          {(data ?? []).length === 0 && (
            <tr>
              <td colSpan={6}>No referrals yet.</td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}
