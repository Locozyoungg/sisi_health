import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";

interface VoucherIssueResponse {
  code: string;
  expires_at: string;
  category: string;
}

interface Reconciliation {
  mismatches: unknown[];
  redeemed_count: number;
  generated_at: string;
}

/** Voucher issuance + reconciliation. Vouchers carry category only — never a
 * medicine name (spec 5.3). */
export default function Vouchers() {
  const queryClient = useQueryClient();
  const [category, setCategory] = useState("sanitary");
  const [amount, setAmount] = useState(300);
  const [lastCode, setLastCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: reconciliation } = useQuery({
    queryKey: ["reconciliation"],
    queryFn: () => api<Reconciliation>("/v1/vouchers/reconciliation"),
  });

  const issue = useMutation({
    mutationFn: () =>
      api<VoucherIssueResponse>("/v1/vouchers/issue", {
        method: "POST",
        body: JSON.stringify({
          school_id: "00000000-0000-0000-0000-000000000001",
          category,
          amount_ksh: amount,
        }),
      }),
    onSuccess: (data) => {
      setLastCode(data.code);
      queryClient.invalidateQueries({ queryKey: ["reconciliation"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "issue failed"),
  });

  return (
    <main className="page page-narrow">
      <header className="page-head">
        <p className="eyebrow">School module</p>
        <h1 className="page-title">Vouchers</h1>
        <p className="page-sub muted">
          Vouchers are issued against a category and reconciled nightly.
        </p>
      </header>

      <div className="card">
        <h2 className="card-title">Issue a voucher</h2>
        <form
          className="form-grid"
          onSubmit={(e) => {
            e.preventDefault();
            issue.mutate();
          }}
        >
          <label className="form-field">
            Category
            <select
              className="input"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="sanitary">Sanitary products</option>
              <option value="otc_pain">OTC pain relief</option>
            </select>
          </label>
          <label className="form-field">
            Amount (KSh)
            <input
              className="input"
              type="number"
              value={amount}
              min={1}
              max={5000}
              onChange={(e) => setAmount(Number(e.target.value))}
            />
          </label>
          <button type="submit" className="btn btn-primary" disabled={issue.isPending}>
            Issue voucher
          </button>
        </form>
        {lastCode && (
          <p className="alert alert-success" data-testid="issued-code">
            Issued: <strong className="mono">{lastCode}</strong>
          </p>
        )}
        {error && (
          <p className="alert alert-danger" role="alert">
            {error}
          </p>
        )}
      </div>

      <div className="card">
        <h2 className="card-title">Reconciliation</h2>
        {reconciliation ? (
          <p className="stat-value" data-testid="recon-count">
            Redemptions: {reconciliation.redeemed_count} · Mismatches:{" "}
            {reconciliation.mismatches.length}
          </p>
        ) : (
          <p className="muted">Loading…</p>
        )}
      </div>
    </main>
  );
}
