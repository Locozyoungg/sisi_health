import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";

interface FacilityRow {
  id: string;
  name: string;
  county: string;
  level: string;
  catchment_counties: string[] | null;
  languages: string[] | null;
  screening_tests: string[] | null;
  estimated_cost_ksh_min: number | null;
  estimated_cost_ksh_max: number | null;
  cost_note: string | null;
  last_verified_at: string | null;
  stale: boolean;
  warning: string | null;
}

const LEVELS = ["", "primary", "secondary", "tertiary"] as const;

/** Facility directory for referrals. Staleness is computed by the API, never
 * stored (spec 5.4.1): an entry not verified in 90 days carries a warning the
 * console must surface before anyone refers to it. */
export default function Facilities() {
  const queryClient = useQueryClient();
  const [county, setCounty] = useState("");
  const [level, setLevel] = useState("");
  const [error, setError] = useState<string | null>(null);

  const params = new URLSearchParams();
  if (county.trim() !== "") params.set("county", county.trim());
  if (level !== "") params.set("level", level);
  const queryString = params.toString();

  const { data, isLoading, error: loadError } = useQuery({
    queryKey: ["facilities", queryString],
    queryFn: () =>
      api<FacilityRow[]>(`/v1/corridor/facilities${queryString === "" ? "" : `?${queryString}`}`),
    refetchInterval: 60_000,
  });

  const verify = useMutation({
    mutationFn: (id: string) =>
      api(`/v1/corridor/facilities/${id}/verify`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["facilities"] }),
    onError: (err) => setError(err instanceof Error ? err.message : "could not verify facility"),
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
        <h1 className="page-title">Facilities</h1>
        <p className="page-sub muted">
          Verify directory entries before referring: details older than 90 days are stale.
        </p>
      </header>
      {error && (
        <p className="alert alert-danger" role="alert">
          {error}
        </p>
      )}

      <div className="card">
        <div className="grid-filters">
          <label className="form-field">
            County
            <input
              className="input"
              data-testid="county-filter"
              value={county}
              onChange={(e) => setCounty(e.target.value)}
              placeholder="all counties"
            />
          </label>
          <label className="form-field">
            Level
            <select
              className="input"
              data-testid="level-filter"
              value={level}
              onChange={(e) => setLevel(e.target.value)}
            >
              {LEVELS.map((option) => (
                <option key={option} value={option}>
                  {option === "" ? "all levels" : option}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className="card table-card">
        <div className="table-scroll">
          <table className="table" data-testid="facility-list">
            <thead>
              <tr>
                <th>Facility</th>
                <th>County</th>
                <th>Level</th>
                <th>Screening</th>
                <th>Cost (KSh)</th>
                <th>Verified</th>
                <th>Directory status</th>
                <th>Verify</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((row) => (
                <tr key={row.id} data-testid="facility-row">
                  <td>{row.name}</td>
                  <td className="muted">{row.county}</td>
                  <td className="muted">{row.level}</td>
                  <td className="muted">{(row.screening_tests ?? []).join(", ") || "—"}</td>
                  <td>
                    {row.estimated_cost_ksh_min === null || row.estimated_cost_ksh_max === null
                      ? "—"
                      : `${row.estimated_cost_ksh_min}–${row.estimated_cost_ksh_max}`}
                  </td>
                  <td className="muted">{row.last_verified_at ?? "never"}</td>
                  <td>
                    {row.stale ? (
                      <span className="badge badge-clay" data-testid="stale-badge">
                        Stale — not verified in the last 90 days
                      </span>
                    ) : (
                      <span className="badge badge-sage" data-testid="fresh-badge">
                        Verified recently
                      </span>
                    )}
                    {row.stale && row.warning && (
                      <p className="warn-text" data-testid="facility-warning">
                        {row.warning}
                      </p>
                    )}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      data-testid="facility-verify-btn"
                      disabled={verify.isPending}
                      onClick={() => {
                        setError(null);
                        verify.mutate(row.id);
                      }}
                    >
                      Verify
                    </button>
                  </td>
                </tr>
              ))}
              {(data ?? []).length === 0 && (
                <tr>
                  <td colSpan={8} className="empty">
                    No facilities match.
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
