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
        <h1 className="page-title">Referrals</h1>
        <p className="page-sub muted">Letters are shared only in the sections the patient approved.</p>
      </header>
      {error && (
        <p className="alert alert-danger" role="alert">
          {error}
        </p>
      )}

      <div className="card">
        <h2 className="card-title">Draft a referral</h2>
        <form
          className="form-grid"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            createReferral.mutate();
          }}
        >
          <label className="form-field">
            Consult request id
            <input
              className="input"
              data-testid="referral-request-id"
              value={requestId}
              onChange={(e) => setRequestId(e.target.value)}
              placeholder="request uuid"
            />
          </label>
          <label className="form-field">
            Facility id (optional)
            <input
              className="input"
              data-testid="referral-facility-id"
              value={facilityId}
              onChange={(e) => setFacilityId(e.target.value)}
              placeholder="facility uuid"
            />
          </label>
          <button
            type="submit"
            className="btn btn-primary"
            data-testid="referral-create-btn"
            disabled={createReferral.isPending}
          >
            Draft referral
          </button>
        </form>
      </div>

      <div className="card table-card">
        <div className="table-scroll">
          <table className="table" data-testid="referral-list">
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
                  <td className="cell-id">{row.id.slice(0, 8)}</td>
                  <td className="cell-id">{row.user_id.slice(0, 8)}</td>
                  <td>
                    <span className="badge badge-neutral">{row.status}</span>
                  </td>
                  <td className="muted">{row.sections.join(", ")}</td>
                  <td>
                    {row.approved_sections && row.approved_sections.length > 0
                      ? row.approved_sections.join(", ")
                      : "—"}
                  </td>
                  <td className="cell-actions">
                    {row.status === "approved" && (
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
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
                      className="btn btn-secondary btn-sm"
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
                  <td colSpan={6} className="empty">
                    No referrals yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
