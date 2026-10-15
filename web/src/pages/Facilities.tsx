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

  if (isLoading) return <main>Loading…</main>;
  if (loadError) return <main role="alert">{String(loadError)}</main>;

  return (
    <main style={{ maxWidth: 1100, margin: "0 auto", padding: 24 }}>
      <h1>Facilities</h1>
      <p>Verify directory entries before referring: details older than 90 days are stale.</p>
      {error && <p role="alert">{error}</p>}

      <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        <label>
          County
          <input
            data-testid="county-filter"
            value={county}
            onChange={(e) => setCounty(e.target.value)}
            placeholder="all counties"
          />
        </label>
        <label>
          Level
          <select
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

      <table data-testid="facility-list">
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
              <td>{row.county}</td>
              <td>{row.level}</td>
              <td>{(row.screening_tests ?? []).join(", ") || "—"}</td>
              <td>
                {row.estimated_cost_ksh_min === null || row.estimated_cost_ksh_max === null
                  ? "—"
                  : `${row.estimated_cost_ksh_min}–${row.estimated_cost_ksh_max}`}
              </td>
              <td>{row.last_verified_at ?? "never"}</td>
              <td>
                {row.stale ? (
                  <span data-testid="stale-badge" style={{ color: "#a33" }}>
                    Stale — not verified in the last 90 days
                  </span>
                ) : (
                  <span data-testid="fresh-badge">Verified recently</span>
                )}
                {row.stale && row.warning && (
                  <p data-testid="facility-warning" style={{ margin: 0, fontSize: 12 }}>
                    {row.warning}
                  </p>
                )}
              </td>
              <td>
                <button
                  type="button"
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
              <td colSpan={8}>No facilities match.</td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}
