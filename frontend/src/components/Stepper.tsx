import { STEP_LABELS } from "./statusMeta";

export default function Stepper({ step, maxStepReached, onJump }: { step: number; maxStepReached: number; onJump: (i: number) => void }) {
  return (
    <div style={{ display: "flex", alignItems: "center", padding: "var(--space-4) var(--space-6)", flex: "none", borderBottom: "1px solid var(--color-divider)" }}>
      {STEP_LABELS.map((label, i) => {
        const done = i < step;
        const current = i === step;
        const reachable = i <= maxStepReached;
        return (
          <div key={label} style={{ display: "flex", alignItems: "center", flex: 1 }}>
            <div onClick={() => reachable && onJump(i)} style={{ display: "flex", alignItems: "center", gap: 8, cursor: reachable ? "pointer" : "default", opacity: reachable ? 1 : 0.4 }}>
              <div
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: "50%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 11,
                  fontWeight: 600,
                  flex: "none",
                  background: done || current ? "var(--color-accent)" : "transparent",
                  color: done || current ? "var(--color-bg)" : "var(--color-text)",
                  border: done || current ? "none" : "1.5px solid var(--color-divider)",
                }}
              >
                {done ? (
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : (
                  i + 1
                )}
              </div>
              <div style={{ fontSize: 12.5, color: current ? "var(--color-text)" : "color-mix(in srgb, var(--color-text) 60%, transparent)", fontWeight: current ? 600 : 400, whiteSpace: "nowrap" }}>{label}</div>
            </div>
            {i < STEP_LABELS.length - 1 && <div style={{ flex: 1, height: 1, margin: "0 10px", background: done ? "var(--color-accent)" : "var(--color-divider)" }} />}
          </div>
        );
      })}
    </div>
  );
}
