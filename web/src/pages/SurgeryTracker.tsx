import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";

interface SurgeryCase {
  id: string;
  user_id: string;
  referral_id: string | null;
  facility_id: string | null;
  gynecologist_id: string | null;
  status: string;
  updated_at: string;
}

interface PricingStub {
  id: string;
  procedure: string;
  facility_id: string;
  amount_ksh_min: number;
  amount_ksh_max: number;
  currency: string;
  indicative: boolean;
  source: string;
}

/** Navigation only: referral -> surgical evaluation -> surgery -> follow-up ->
 * closed (plus cancelled). The console records status and generic outcome
 * categories; it never makes a clinical decision. Pricing is indicative and
 * always sourced (spec 5.4). */
const TRANSITIONS: Record<string, string[]> = {
  diagnostic: ["surgical_evaluation", "cancelled"],
  surgical_evaluation: ["surgery", "cancelled"],
  surgery: ["follow_up", "cancelled"],
  follow_up: ["closed", "cancelled"],
  closed: [],
  cancelled: [],
};

const OUTCOME_CATEGORIES = [
  "completed_surgery",
  "follow_up_scheduled",
  "referred_on",
  "cancelled",
  "no_show",
] as const;

export default function SurgeryTracker() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [outcomeDraft, setOutcomeDraft] = useState<Record<string, string>>({});
  const [procedure, setProcedure] = useState("");
  const [facilityId, setFacilityId] = useState("");
  const [amountMin, setAmountMin] = useState(0);
  const [amountMax, setAmountMax] = useState(0);
  const [source, setSource] = useState("");
  const [note, setNote] = useState("");

  const { data: cases, isLoading, error: loadError } = useQuery({
    queryKey: ["surgery-cases"],
    queryFn: () => api<SurgeryCase[]>("/v1/corridor/surgery/cases"),
    refetchInterval: 30_000,
  });

  const { data: pricing } = useQuery({
    queryKey: ["pricing-stubs"],
    queryFn: () => api<PricingStub[]>("/v1/corridor/surgery/pricing-stubs"),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["surgery-cases"] });
    queryClient.invalidateQueries({ queryKey: ["pricing-stubs"] });
  };

  const transition = useMutation({
    mutationFn: (input: { id: string; to_status: string }) =>
      api(`/v1/corridor/surgery/cases/${input.id}/transition`, {
        method: "POST",
        body: JSON.stringify({ to_status: input.to_status }),
      }),
    onSuccess: refresh,
    onError: (err) => setError(err instanceof Error ? err.message : "transition failed"),
  });

  const addOutcome = useMutation({
    mutationFn: (input: { id: string; outcome_category: string }) =>
      api(`/v1/corridor/surgery/cases/${input.id}/outcomes`, {
        method: "POST",
        body: JSON.stringify({ outcome_category: input.outcome_category }),
      }),
    onSuccess: refresh,
    onError: (err) => setError(err instanceof Error ? err.message : "could not log outcome"),
  });

  const addPricing = useMutation({
    mutationFn: () =>
      api<PricingStub>("/v1/corridor/surgery/pricing-stubs", {
        method: "POST",
        body: JSON.stringify({
          procedure: procedure.trim(),
          facility_id: facilityId.trim(),
          amount_ksh_min: amountMin,
          amount_ksh_max: amountMax,
          source: source.trim(),
          note: note.trim() === "" ? null : note.trim(),
        }),
      }),
    onSuccess: refresh,
    onError: (err) => setError(err instanceof Error ? err.message : "could not save pricing stub"),
  });

  if (isLoading) return <main>Loading…</main>;
  if (loadError) return <main role="alert">{String(loadError)}</main>;

  return (
    <main style={{ maxWidth: 1100, margin: "0 auto", padding: 24 }}>
      <h1>Surgery navigation</h1>
      <p>Navigation and follow-up only — never a clinical decision.</p>
      {error && <p role="alert">{error}</p>}

      <table data-testid="surgery-cases">
        <thead>
          <tr>
            <th>Case</th>
            <th>Patient</th>
            <th>Facility</th>
            <th>Status</th>
            <th>Move to</th>
            <th>Outcome</th>
          </tr>
        </thead>
        <tbody>
          {(cases ?? []).map((row) => {
            const allowed = TRANSITIONS[row.status] ?? [];
            const draft = outcomeDraft[row.id] ?? OUTCOME_CATEGORIES[0];
            return (
              <tr key={row.id} data-testid="surgery-row">
                <td>{row.id.slice(0, 8)}</td>
                <td>{row.user_id.slice(0, 8)}</td>
                <td>{row.facility_id ? row.facility_id.slice(0, 8) : "—"}</td>
                <td data-testid="surgery-status">{row.status}</td>
                <td>
                  <select
                    key={row.status}
                    data-testid="surgery-transition"
                    defaultValue=""
                    disabled={allowed.length === 0}
                    aria-label={`transition for ${row.id.slice(0, 8)}`}
                    onChange={(e) => {
                      if (e.target.value) {
                        setError(null);
                        transition.mutate({ id: row.id, to_status: e.target.value });
                      }
                    }}
                  >
                    <option value="" disabled>
                      {allowed.length === 0 ? "closed" : "select status"}
                    </option>
                    {allowed.map((status) => (
                      <option key={status} value={status}>
                        {status}
                      </option>
                    ))}
                  </select>
                </td>
                <td style={{ display: "flex", gap: 8 }}>
                  <select
                    data-testid="surgery-outcome-select"
                    value={draft}
                    aria-label={`outcome for ${row.id.slice(0, 8)}`}
                    onChange={(e) =>
                      setOutcomeDraft((prev) => ({ ...prev, [row.id]: e.target.value }))
                    }
                  >
                    {OUTCOME_CATEGORIES.map((category) => (
                      <option key={category} value={category}>
                        {category}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    data-testid="surgery-outcome-btn"
                    disabled={addOutcome.isPending}
                    onClick={() => {
                      setError(null);
                      addOutcome.mutate({ id: row.id, outcome_category: draft });
                    }}
                  >
                    Log
                  </button>
                </td>
              </tr>
            );
          })}
          {(cases ?? []).length === 0 && (
            <tr>
              <td colSpan={6}>No cases tracked.</td>
            </tr>
          )}
        </tbody>
      </table>

      <h2>Indicative pricing stubs</h2>
      <form
        style={{ display: "grid", gap: 12, maxWidth: 420, marginBottom: 16 }}
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          addPricing.mutate();
        }}
      >
        <label>
          Procedure
          <input
            data-testid="pricing-procedure"
            value={procedure}
            onChange={(e) => setProcedure(e.target.value)}
          />
        </label>
        <label>
          Facility id
          <input
            data-testid="pricing-facility"
            value={facilityId}
            onChange={(e) => setFacilityId(e.target.value)}
            placeholder="facility uuid"
          />
        </label>
        <label>
          Amount min (KSh)
          <input
            type="number"
            data-testid="pricing-min"
            value={amountMin}
            min={0}
            onChange={(e) => setAmountMin(Number(e.target.value))}
          />
        </label>
        <label>
          Amount max (KSh)
          <input
            type="number"
            data-testid="pricing-max"
            value={amountMax}
            min={0}
            onChange={(e) => setAmountMax(Number(e.target.value))}
          />
        </label>
        <label>
          Source (required)
          <input
            data-testid="pricing-source"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            placeholder="e.g. facility price list, March 2026"
          />
        </label>
        <label>
          Note
          <input value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button type="submit" data-testid="pricing-submit" disabled={addPricing.isPending}>
          Save pricing stub
        </button>
      </form>

      <table data-testid="pricing-list">
        <thead>
          <tr>
            <th>Procedure</th>
            <th>Facility</th>
            <th>Range (KSh)</th>
            <th>Source</th>
            <th>Indicative</th>
          </tr>
        </thead>
        <tbody>
          {(pricing ?? []).map((row) => (
            <tr key={row.id} data-testid="pricing-row">
              <td>{row.procedure}</td>
              <td>{row.facility_id.slice(0, 8)}</td>
              <td>
                {row.amount_ksh_min}–{row.amount_ksh_max}
              </td>
              <td>{row.source}</td>
              <td>{row.indicative ? "yes" : "no"}</td>
            </tr>
          ))}
          {(pricing ?? []).length === 0 && (
            <tr>
              <td colSpan={5}>No pricing stubs recorded.</td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}
