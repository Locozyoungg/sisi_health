import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { bandClass } from "../ui";

interface QueueRow {
  request_id: string;
  pseudonym: string;
  band: string;
  urgent: boolean;
  safeguarding: boolean;
  age_band: string;
  status: string;
  chaperone_requested: boolean;
  preferred_language: string;
  created_at: string;
}

function flags(row: QueueRow): string {
  const parts = [
    row.urgent ? "urgent" : null,
    row.safeguarding ? "safeguarding" : null,
    row.chaperone_requested ? "chaperone requested" : null,
  ].filter((part): part is string => part !== null);
  return parts.length > 0 ? parts.join(", ") : "—";
}

/** The specialist corridor queue: pseudonyms, bands and flags only. The
 * encrypted case snapshot is opened on the case view alone, never listed here
 * (non-negotiable 5; asserted by the Playwright e2e). */
export default function CorridorQueue() {
  const navigate = useNavigate();
  const { data, isLoading, error } = useQuery({
    queryKey: ["corridor-queue"],
    queryFn: () => api<QueueRow[]>("/v1/corridor/queue"),
    refetchInterval: 30_000,
  });

  if (isLoading) {
    return (
      <main className="page">
        <p className="muted">Loading…</p>
      </main>
    );
  }
  if (error) {
    return (
      <main className="page" role="alert">
        <p className="alert alert-danger">{String(error)}</p>
      </main>
    );
  }

  return (
    <main className="page">
      <header className="page-head">
        <p className="eyebrow">Specialist corridor</p>
        <h1 className="page-title">Corridor queue</h1>
        <p className="page-sub muted">Corridor staff see pseudonyms, bands and flags only.</p>
      </header>

      <div className="card table-card">
        <div className="table-scroll">
          <table className="table" data-testid="corridor-queue">
            <thead>
              <tr>
                <th>Client</th>
                <th>Band</th>
                <th>Age band</th>
                <th>Status</th>
                <th>Flags</th>
                <th>Language</th>
                <th>Requested</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((row) => (
                <tr
                  key={row.request_id}
                  data-testid="corridor-row"
                  className="row-link"
                  tabIndex={0}
                  onClick={() => navigate(`/corridor/${row.request_id}`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") navigate(`/corridor/${row.request_id}`);
                  }}
                >
                  <td className="cell-id">{row.pseudonym.slice(0, 8)}</td>
                  <td>
                    <span className={bandClass(row.band)}>{row.band}</span>
                  </td>
                  <td>{row.age_band}</td>
                  <td>
                    <span className="badge badge-neutral">{row.status}</span>
                  </td>
                  <td>{flags(row)}</td>
                  <td className="muted">{row.preferred_language}</td>
                  <td className="muted">{row.created_at}</td>
                </tr>
              ))}
              {(data ?? []).length === 0 && (
                <tr>
                  <td colSpan={7} className="empty">
                    Queue is empty.
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
