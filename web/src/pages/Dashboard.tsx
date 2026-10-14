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

  if (isLoading) return <main>Loading…</main>;
  if (error) return <main role="alert">{String(error)}</main>;
  if (!data || !data.enough_data) {
    return (
      <main style={{ maxWidth: 900, margin: "0 auto", padding: 24 }}>
        <h1>School dashboard</h1>
        <p data-testid="not-enough">Not enough data yet</p>
      </main>
    );
  }

  return (
    <main style={{ maxWidth: 900, margin: "0 auto", padding: 24 }}>
      <h1>School dashboard — {data.term}</h1>
      <table data-testid="dashboard-cells">
        <tbody>
          {Object.entries(data.cells).map(([key, value]) => (
            <tr key={key}>
              <td>{key}</td>
              <td>{value === null ? "—" : String(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
