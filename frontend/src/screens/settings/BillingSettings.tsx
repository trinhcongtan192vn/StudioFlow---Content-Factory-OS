import { Fragment, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { BudgetOut } from "../../api/types";

interface DetailRow {
  project: string;
  provider: string;
  request_count: number;
  cost_total: number;
  requests: { time: string; model: string; tokens_label: string; cost: number }[];
}

export default function BillingSettings() {
  const [budget, setBudget] = useState<BudgetOut[]>([]);
  const [detailChannel, setDetailChannel] = useState<{ id: string; name: string } | null>(null);

  useEffect(() => {
    api.getBudget().then(setBudget);
  }, []);

  async function updateSoftLimit(channelId: string, v: number) {
    setBudget((b) => b.map((x) => (x.channel_id === channelId ? { ...x, soft_limit: v } : x)));
    await api.patchBudget(channelId, { soft_limit: v });
  }
  async function updateThreshold(channelId: string, v: number) {
    setBudget((b) => b.map((x) => (x.channel_id === channelId ? { ...x, threshold_pct: v } : x)));
    await api.patchBudget(channelId, { threshold_pct: v });
  }

  if (detailChannel) {
    return <BillingDetail channelId={detailChannel.id} channelName={detailChannel.name} onBack={() => setDetailChannel(null)} />;
  }

  const totalSpend = budget.reduce((s, b) => s + b.spent, 0);
  const totalBudget = budget.reduce((s, b) => s + b.soft_limit, 0);

  return (
    <div>
      <h3 style={{ marginBottom: 2 }}>Chi phí &amp; Ngân sách</h3>
      <p style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 13, marginBottom: "var(--space-4)" }}>Chi phí API theo kênh, chu kỳ hiện tại.</p>

      <div className="card elev-sm" style={{ flexDirection: "row", gap: "var(--space-6)", marginBottom: "var(--space-4)", maxWidth: 560 }}>
        <div>
          <div style={{ fontSize: 11, opacity: 0.55 }}>Tổng chi tháng này</div>
          <div style={{ fontFamily: "var(--font-heading)", fontSize: 20, fontWeight: 600 }}>
            ${totalSpend.toFixed(2)}
            <span style={{ fontSize: 13, opacity: 0.5 }}> / ${totalBudget.toFixed(2)}</span>
          </div>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", maxWidth: 560 }}>
        {budget.map((b) => (
          <div key={b.channel_id} className="card" style={{ gap: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <div className="card-title" style={{ fontSize: 14 }}>
                {b.channel_name}
              </div>
              <div style={{ fontSize: 13, fontFamily: "ui-monospace,monospace" }}>
                ${b.spent.toFixed(2)} / ${b.soft_limit.toFixed(2)}
              </div>
            </div>
            <div style={{ height: 6, borderRadius: 4, background: "var(--color-neutral-800)", overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${b.soft_limit > 0 ? Math.min(100, (b.spent / b.soft_limit) * 100) : 0}%`, background: b.over_threshold ? "var(--color-warning)" : "var(--color-accent)" }} />
            </div>
            {b.over_threshold && <div style={{ fontSize: 12, color: "var(--color-warning)" }}>⚠ Đã vượt {b.threshold_pct}% ngân sách — cảnh báo đã gửi</div>}
            <div style={{ display: "flex", gap: "var(--space-3)", marginTop: 2, alignItems: "flex-end" }}>
              <div className="field" style={{ flex: 1 }}>
                <label>Hạn mức ($)</label>
                <input className="input" type="number" min={0} step={0.5} defaultValue={b.soft_limit} onBlur={(e) => updateSoftLimit(b.channel_id, parseFloat(e.target.value) || 0)} />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>Ngưỡng cảnh báo (%)</label>
                <input className="input" type="number" min={1} max={100} defaultValue={b.threshold_pct} onBlur={(e) => updateThreshold(b.channel_id, parseInt(e.target.value) || 0)} />
              </div>
              <button className="btn btn-secondary" style={{ fontSize: 12, padding: "8px 12px" }} onClick={() => setDetailChannel({ id: b.channel_id, name: b.channel_name })}>
                Xem chi tiết →
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function BillingDetail({ channelId, channelName, onBack }: { channelId: string; channelName: string; onBack: () => void }) {
  const [rows, setRows] = useState<DetailRow[] | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    api.getBudgetDetail(channelId).then((r) => setRows(r.rows));
  }, [channelId]);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: "var(--space-1)" }}>
        <div onClick={onBack} style={{ display: "flex", alignItems: "center", gap: 5, cursor: "pointer", color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 12 }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </svg>
          Chi phí &amp; Ngân sách
        </div>
      </div>
      <h3 style={{ marginBottom: 2 }}>{channelName} — chi tiết chi phí</h3>
      <p style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 13, marginBottom: "var(--space-4)" }}>Theo từng project, breakdown theo từng request AI.</p>

      {rows === null ? (
        <div style={{ opacity: 0.6 }}>Đang tải...</div>
      ) : rows.length === 0 ? (
        <div style={{ opacity: 0.6, fontSize: 13 }}>Chưa có lệnh gọi AI nào ghi nhận chi phí cho kênh này.</div>
      ) : (
        <table className="table" style={{ marginBottom: "var(--space-2)" }}>
          <thead>
            <tr>
              <th>Project</th>
              <th>Provider</th>
              <th>Số request</th>
              <th>Chi phí</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <Fragment key={i}>
                <tr onClick={() => setExpanded(expanded === i ? null : i)} style={{ cursor: "pointer" }}>
                  <td>{r.project}</td>
                  <td>
                    <span className="tag tag-neutral">{r.provider}</span>
                  </td>
                  <td>{r.request_count}</td>
                  <td style={{ fontFamily: "ui-monospace,monospace" }}>${r.cost_total.toFixed(4)}</td>
                </tr>
                {expanded === i && (
                  <tr>
                    <td colSpan={4} style={{ background: "var(--color-neutral-900)" }}>
                      <div style={{ display: "flex", flexDirection: "column", gap: 4, padding: "4px 0" }}>
                        {r.requests.map((req, j) => (
                          <div key={j} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, opacity: 0.8 }}>
                            <span>
                              {req.time} · {req.model} · {req.tokens_label}
                            </span>
                            <span style={{ fontFamily: "ui-monospace,monospace" }}>${req.cost.toFixed(4)}</span>
                          </div>
                        ))}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
