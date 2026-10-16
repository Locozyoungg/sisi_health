import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

interface DashboardData {
  enough_data: boolean;
  message: string | null;
  term: string;
  school_id: string;
  cells: Record<string, number | null>;
}

/** The k-anonymized school dashboard: suppressed cells render as a dash, and
 * below threshold it says "not enough data yet" — never a zero (spec 3.4). */
export default function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<DashboardData>("/v1/school/dashboard?school_id=00000000-0000-0000-0000-000000000001"),
  });

  if (isLoading) {
    return (
      <main className="page page-narrow">
        <p className="muted">Loading…</p>
      </main>
    );
  }
  if (error) {
    return (
      <main className="page page-narrow" role="alert">
        <p className="alert alert-danger">{String(error)}</p>
      </main>
    );
  }
  if (!data || !data.enough_data) {
    return (
      <main className="page page-narrow">
        <header className="page-head">
          <p className="eyebrow">School module</p>
          <h1 className="page-title">School dashboard</h1>
        </header>
        <div className="card">
          <p className="eyebrow">Term aggregate</p>
          <p className="notice" data-testid="not-enough">
            Not enough data yet
          </p>
          <p className="muted">
            Cells stay hidden until enough students have completed assessments this term, so no
            individual can be picked out of the totals.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="page page-narrow">
      <header className="page-head">
        <p className="eyebrow">School module</p>
        <h1 className="page-title">School dashboard — {data.term}</h1>
      </header>
      <div className="card table-card">
        <div className="table-scroll">
          <table className="table" data-testid="dashboard-cells">
            <tbody>
              {Object.entries(data.cells).map(([key, value]) => (
                <tr key={key}>
                  <td>{key}</td>
                  <td>{value === null ? "—" : String(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
