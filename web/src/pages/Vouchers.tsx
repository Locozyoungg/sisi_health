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
    <main style={{ maxWidth: 900, margin: "0 auto", padding: 24 }}>
      <h1>Vouchers</h1>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          issue.mutate();
        }}
        style={{ display: "grid", gap: 12, maxWidth: 420 }}
      >
        <label>
          Category
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="sanitary">Sanitary products</option>
            <option value="otc_pain">OTC pain relief</option>
          </select>
        </label>
        <label>
          Amount (KSh)
          <input
            type="number"
            value={amount}
            min={1}
            max={5000}
            onChange={(e) => setAmount(Number(e.target.value))}
          />
        </label>
        <button type="submit" disabled={issue.isPending}>
          Issue voucher
        </button>
      </form>
      {lastCode && (
        <p data-testid="issued-code">
          Issued: <strong>{lastCode}</strong>
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <h2>Reconciliation</h2>
      {reconciliation && (
        <p data-testid="recon-count">
          Redemptions: {reconciliation.redeemed_count} · Mismatches: {reconciliation.mismatches.length}
        </p>
      )}
    </main>
  );
}
