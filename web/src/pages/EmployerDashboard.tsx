import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

/** The seeded demo employer (backend/scripts/seed_employer_demo.py) — the console
 * points at a fixed id the same way the school dashboard does. */
const EMPLOYER_ID = "00000000-0000-0000-0000-0000000000e1";

interface WalletData {
  employer_id: string;
  balance_ksh: number;
  updated_at: string | null;
}

interface DashboardData {
  enough_data: boolean;
  message: string | null;
  term: string;
  employer_id: string;
  cells: Record<string, number | null>;
}

/** The employer console (Phase 7): the bound employer's wallet balance plus the
 * k-anonymized dashboard. Aggregate cells only — never employee-level data.
 * Suppressed cells render as a dash, and below threshold it says "not enough
 * data yet" — never a zero (spec 3.4). */
export default function EmployerDashboard() {
  const wallet = useQuery({
    queryKey: ["employer-wallet"],
    queryFn: () => api<WalletData>(`/v1/employers/${EMPLOYER_ID}/wallet`),
    retry: false, // a 403 permission error is not transient — surface it at once
  });
  const dashboard = useQuery({
    queryKey: ["employer-dashboard"],
    queryFn: () => api<DashboardData>(`/v1/employers/${EMPLOYER_ID}/dashboard?term=2026-T1`),
    retry: false,
  });

  if (wallet.isLoading || dashboard.isLoading) return <main>Loading…</main>;
  const error = wallet.error ?? dashboard.error;
  if (error) {
    // A role without employer:wallet / employer:dashboard lands here (403).
    return (
      <main role="alert" data-testid="employer-role-alert">
        {String(error)}
      </main>
    );
  }
  if (!wallet.data || !dashboard.data) return <main>Loading…</main>;

  return (
    <main style={{ maxWidth: 900, margin: "0 auto", padding: 24 }}>
      <h1>Employer dashboard — {dashboard.data.term}</h1>
      <p data-testid="employer-wallet-balance">
        Wallet balance: {wallet.data.balance_ksh.toLocaleString("en-KE")} KES
      </p>
      {!dashboard.data.enough_data ? (
        <p data-testid="not-enough">Not enough data yet</p>
      ) : (
        <table data-testid="employer-dashboard-cells">
          <tbody>
            {Object.entries(dashboard.data.cells).map(([key, value]) => (
              <tr key={key}>
                <td>{key}</td>
                <td>{value === null ? "—" : String(value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
