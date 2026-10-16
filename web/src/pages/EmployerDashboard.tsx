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

  if (wallet.isLoading || dashboard.isLoading) {
    return (
      <main className="page page-narrow">
        <p className="muted">Loading…</p>
      </main>
    );
  }
  const error = wallet.error ?? dashboard.error;
  if (error) {
    // A role without employer:wallet / employer:dashboard lands here (403).
    return (
      <main className="page page-narrow" role="alert" data-testid="employer-role-alert">
        <header className="page-head">
          <p className="eyebrow">Employer module</p>
          <h1 className="page-title">Employer dashboard</h1>
        </header>
        <p className="alert alert-danger">{String(error)}</p>
      </main>
    );
  }
  if (!wallet.data || !dashboard.data) {
    return (
      <main className="page page-narrow">
        <p className="muted">Loading…</p>
      </main>
    );
  }

  return (
    <main className="page page-narrow">
      <header className="page-head">
        <p className="eyebrow">Employer module</p>
        <h1 className="page-title">Employer dashboard — {dashboard.data.term}</h1>
        <p className="page-sub muted">
          Aggregate view only: employee-level detail never leaves the clinic.
        </p>
      </header>

      <div className="card">
        <p className="eyebrow">Wallet</p>
        <p className="stat-value" data-testid="employer-wallet-balance">
          Wallet balance:{" "}
          <strong className="amount">{wallet.data.balance_ksh.toLocaleString("en-KE")}</strong> KES
        </p>
      </div>

      <div className="card table-card">
        {!dashboard.data.enough_data ? (
          <div className="table-card-body">
            <p className="eyebrow">Health aggregate</p>
            <p className="notice" data-testid="not-enough">
              Not enough data yet
            </p>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="table" data-testid="employer-dashboard-cells">
              <tbody>
                {Object.entries(dashboard.data.cells).map(([key, value]) => (
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
