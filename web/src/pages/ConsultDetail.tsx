import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { bandClass } from "../ui";

interface ConsentRow {
  kind: string;
  method: string;
  captured_at: string;
}

interface ConsultDetailData {
  request_id: string;
  pseudonym: string;
  age_band: string;
  status: string;
  band: string;
  indicators: string[];
  urgent: boolean;
  safeguarding: boolean;
  features: Record<string, unknown>;
  consents: ConsentRow[];
  chaperone_requested: boolean;
  preferred_county: string | null;
  preferred_language: string;
}

/** The scheduled session as the staff member last saw it. The corridor API has
 * no session read endpoint (the room name is one-time, never reused), so the
 * schedule response and the start response are kept for this request only. */
interface SessionState {
  sessionId: string;
  roomName: string;
  status: string;
  joinUrl: string | null;
  token: string | null;
}

const SESSION_KEY_PREFIX = "sisi_corridor_session_";
const CONSENT_KINDS = [
  "guardian_consent",
  "minor_assent",
  "chaperone_requested",
  "chaperone_confirmed",
] as const;
const CONSENT_METHODS = ["digital", "sms_link", "paper", "voice"] as const;
const OUTCOMES = ["completed", "no_show"] as const;

function readSession(requestId: string): SessionState | null {
  const raw = sessionStorage.getItem(SESSION_KEY_PREFIX + requestId);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SessionState;
  } catch {
    return null;
  }
}

function writeSession(requestId: string, next: SessionState | null): void {
  if (next === null) sessionStorage.removeItem(SESSION_KEY_PREFIX + requestId);
  else sessionStorage.setItem(SESSION_KEY_PREFIX + requestId, JSON.stringify(next));
}

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** Case view for one corridor request: band, flags, the decrypted feature
 * snapshot (computed aggregates only), recorded consents, nurse review, the
 * gynecologist session, and minor consent/chaperone recording. */
export default function ConsultDetail() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [gynecologistId, setGynecologistId] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [modality, setModality] = useState<string>("video");
  const [outcome, setOutcome] = useState<string>(OUTCOMES[0]);
  const [consentKind, setConsentKind] = useState<string>(CONSENT_KINDS[0]);
  const [consentMethod, setConsentMethod] = useState<string>(CONSENT_METHODS[0]);
  const [session, setSession] = useState<SessionState | null>(() => readSession(id));

  const { data, isLoading, error: loadError } = useQuery({
    queryKey: ["consult", id],
    queryFn: () => api<ConsultDetailData>(`/v1/corridor/consults/${id}`),
    enabled: id !== "",
  });

  function updateSession(next: SessionState | null): void {
    setSession(next);
    writeSession(id, next);
  }

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["consult", id] });

  const review = useMutation({
    mutationFn: (decision: "approved" | "declined") =>
      api(`/v1/corridor/consults/${id}/review`, {
        method: "POST",
        body: JSON.stringify({ decision }),
      }),
    onSuccess: () => {
      refresh();
      queryClient.invalidateQueries({ queryKey: ["corridor-queue"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "review failed"),
  });

  const schedule = useMutation({
    mutationFn: () =>
      api<{ session_id: string; room_name: string; status: string }>(
        `/v1/corridor/consults/${id}/schedule`,
        {
          method: "POST",
          body: JSON.stringify({
            gynecologist_id: gynecologistId.trim(),
            scheduled_at: new Date(scheduledAt).toISOString(),
            modality,
          }),
        },
      ),
    onSuccess: (result) => {
      updateSession({
        sessionId: result.session_id,
        roomName: result.room_name,
        status: result.status,
        joinUrl: null,
        token: null,
      });
      refresh();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "schedule failed"),
  });

  const startSession = useMutation({
    mutationFn: (current: SessionState) =>
      api<{ session_id: string; room: string; domain: string; token: string; join_url: string }>(
        `/v1/corridor/sessions/${current.sessionId}/start`,
        { method: "POST" },
      ),
    onSuccess: (result, current) =>
      updateSession({
        ...current,
        roomName: result.room,
        status: "in_progress",
        joinUrl: result.join_url,
        token: result.token,
      }),
    onError: (err) => setError(err instanceof Error ? err.message : "could not start session"),
  });

  const completeSession = useMutation({
    mutationFn: (input: { current: SessionState; outcome: string }) =>
      api<{ session_id: string; status: string }>(
        `/v1/corridor/sessions/${input.current.sessionId}/complete`,
        { method: "POST", body: JSON.stringify({ outcome: input.outcome }) },
      ),
    onSuccess: (result, input) => {
      updateSession({ ...input.current, status: result.status });
      refresh();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "could not complete session"),
  });

  const recordConsent = useMutation({
    mutationFn: () =>
      api(`/v1/corridor/consults/${id}/consents`, {
        method: "POST",
        body: JSON.stringify({ kind: consentKind, method: consentMethod }),
      }),
    onSuccess: refresh,
    onError: (err) => setError(err instanceof Error ? err.message : "could not record consent"),
  });

  if (isLoading) {
    return (
      <main className="page page-narrow">
        <p className="muted">Loading…</p>
      </main>
    );
  }
  if (loadError) {
    return (
      <main className="page page-narrow" role="alert">
        <p className="alert alert-danger">{String(loadError)}</p>
      </main>
    );
  }
  if (!data) {
    return (
      <main className="page page-narrow">
        <p className="muted">No request loaded.</p>
      </main>
    );
  }

  const canStart = session !== null && session.status === "scheduled";
  const canComplete = session !== null && session.status === "in_progress";

  return (
    <main className="page page-narrow">
      <header className="page-head">
        <p className="eyebrow">Specialist corridor</p>
        <h1 className="page-title">Consult request</h1>
      </header>
      {error && (
        <p className="alert alert-danger" role="alert">
          {error}
        </p>
      )}

      <section className="card">
        <h2 className="card-title" data-testid="consult-section">
          Case
        </h2>
        <div className="facts">
          <p className="fact">
            Client: <strong className="mono">{data.pseudonym.slice(0, 8)}</strong> · Age band:{" "}
            {data.age_band} · Language: {data.preferred_language}
            {data.preferred_county ? ` · County: ${data.preferred_county}` : ""}
          </p>
          <p className="fact">
            Band: <span className={bandClass(data.band)}>{data.band}</span> · Status:{" "}
            <strong data-testid="consult-status">{data.status}</strong>
          </p>
          <p className="fact">
            Flags: {data.urgent ? "urgent" : "not urgent"} ·{" "}
            {data.safeguarding ? "safeguarding" : "no safeguarding flag"} ·{" "}
            {data.chaperone_requested ? "chaperone requested" : "no chaperone request"}
          </p>
          <p className="fact">
            Indicators:{" "}
            <span data-testid="consult-indicators">
              {data.indicators.length > 0 ? data.indicators.join(", ") : "none reported"}
            </span>
          </p>
        </div>
      </section>

      <section className="card table-card">
        <h2 className="card-title">Feature snapshot</h2>
        <div className="table-scroll">
          <table className="table" data-testid="consult-features">
            <tbody>
              {Object.entries(data.features).map(([key, value]) => (
                <tr key={key}>
                  <td className="muted">{key}</td>
                  <td>{renderValue(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2 className="card-title">Recorded consents</h2>
        <ul className="list" data-testid="consult-consents">
          {data.consents.map((consent, index) => (
            <li key={`${consent.kind}-${index}`}>
              {consent.kind} · {consent.method} ·{" "}
              <span className="muted">{consent.captured_at}</span>
            </li>
          ))}
          {data.consents.length === 0 && <li className="muted">No consents recorded.</li>}
        </ul>
        <div className="form-grid">
          <label className="form-field">
            Consent kind
            <select
              className="input"
              data-testid="consent-kind"
              value={consentKind}
              onChange={(e) => setConsentKind(e.target.value)}
            >
              {CONSENT_KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {kind}
                </option>
              ))}
            </select>
          </label>
          <label className="form-field">
            Method
            <select
              className="input"
              data-testid="consent-method"
              value={consentMethod}
              onChange={(e) => setConsentMethod(e.target.value)}
            >
              {CONSENT_METHODS.map((method) => (
                <option key={method} value={method}>
                  {method}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn btn-secondary"
            data-testid="consent-btn"
            disabled={recordConsent.isPending}
            onClick={() => {
              setError(null);
              recordConsent.mutate();
            }}
          >
            Record consent
          </button>
        </div>
      </section>

      <section className="card">
        <h2 className="card-title">Nurse review</h2>
        <div className="actions">
          <button
            type="button"
            className="btn btn-primary"
            data-testid="approve-btn"
            disabled={review.isPending}
            onClick={() => {
              setError(null);
              review.mutate("approved");
            }}
          >
            Approve
          </button>
          <button
            type="button"
            className="btn btn-danger"
            data-testid="decline-btn"
            disabled={review.isPending}
            onClick={() => {
              setError(null);
              review.mutate("declined");
            }}
          >
            Decline
          </button>
        </div>
      </section>

      <section className="card">
        <h2 className="card-title">Schedule with a gynecologist</h2>
        <form
          className="form-grid"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            if (gynecologistId.trim() === "" || scheduledAt === "") {
              setError("gynecologist id and a scheduled time are required");
              return;
            }
            schedule.mutate();
          }}
        >
          <label className="form-field">
            Gynecologist id
            <input
              className="input"
              data-testid="gynecologist-id"
              value={gynecologistId}
              onChange={(e) => setGynecologistId(e.target.value)}
              placeholder="staff uuid"
            />
          </label>
          <label className="form-field">
            Scheduled at
            <input
              className="input"
              type="datetime-local"
              data-testid="scheduled-at"
              value={scheduledAt}
              onChange={(e) => setScheduledAt(e.target.value)}
            />
          </label>
          <label className="form-field">
            Modality
            <select
              className="input"
              data-testid="modality"
              value={modality}
              onChange={(e) => setModality(e.target.value)}
            >
              <option value="video">video</option>
              <option value="audio">audio</option>
            </select>
          </label>
          <button type="submit" className="btn btn-primary" data-testid="schedule-btn" disabled={schedule.isPending}>
            Schedule
          </button>
        </form>
      </section>

      {session && (
        <section className="card">
          <h2 className="card-title">Session</h2>
          <div className="facts">
            <p className="fact">
              Session id:{" "}
              <strong className="mono" data-testid="session-id">
                {session.sessionId}
              </strong>{" "}
              · Status: <strong data-testid="session-status">{session.status}</strong>
            </p>
            <p className="fact">
              Room: <span className="mono">{session.roomName}</span>
            </p>
          </div>
          <div className="actions mt-4">
            <button
              type="button"
              className="btn btn-primary"
              data-testid="session-start-btn"
              disabled={!canStart || startSession.isPending}
              onClick={() => {
                setError(null);
                startSession.mutate(session);
              }}
            >
              Start session
            </button>
            {session.joinUrl && (
              <a
                className="btn btn-secondary"
                data-testid="room-link"
                href={session.joinUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open the consult room
              </a>
            )}
          </div>
          {session.token && (
            <p className="fact mono break-all muted" data-testid="room-token">
              Room token: {session.token}
            </p>
          )}
          <div className="actions actions-end mt-4">
            <label className="form-field">
              Outcome
              <select
                className="input input-compact"
                data-testid="session-outcome"
                value={outcome}
                onChange={(e) => setOutcome(e.target.value)}
              >
                {OUTCOMES.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="btn btn-secondary"
              data-testid="session-complete-btn"
              disabled={!canComplete || completeSession.isPending}
              onClick={() => {
                setError(null);
                completeSession.mutate({ current: session, outcome });
              }}
            >
              Complete session
            </button>
          </div>
        </section>
      )}
    </main>
  );
}
