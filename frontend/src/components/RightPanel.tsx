import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { BrandProfile, ProjectSummary } from "../api/types";
import { useApp } from "../store/AppContext";

export default function RightPanel({ channelId, project }: { channelId: string; project: ProjectSummary | null }) {
  const app = useApp();
  const [profile, setProfile] = useState<BrandProfile | null>(null);

  useEffect(() => {
    api.getBrandProfile(channelId).then(setProfile).catch(() => setProfile(null));
  }, [channelId]);

  if (!app.rightPanelOpen) {
    return (
      <div style={{ width: 32, flex: "none", borderLeft: "1px solid var(--color-divider)" }}>
        <div style={{ padding: "var(--space-3) 0", display: "flex", justifyContent: "center" }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" onClick={app.toggleRightPanel} style={{ cursor: "pointer", opacity: 0.6 }}>
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </div>
      </div>
    );
  }

  return (
    <div style={{ width: 280, flex: "none", borderLeft: "1px solid var(--color-divider)", overflow: "hidden" }}>
      <div style={{ padding: "var(--space-4)", overflowY: "auto", height: "100%" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--space-3)" }}>
          <h6 style={{ margin: 0 }}>BrandProfile</h6>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" onClick={app.toggleRightPanel} style={{ cursor: "pointer", opacity: 0.6 }}>
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </div>
        {profile && (
          <>
            <div style={{ fontSize: 13, lineHeight: 1.5, marginBottom: "var(--space-3)" }}>
              {profile.brand_voice.tone}
              {profile.brand_voice.pacing ? ` — nhịp ${profile.brand_voice.pacing}` : ""}
            </div>
            <div style={{ marginBottom: "var(--space-3)" }}>
              <div style={{ fontSize: 11, color: "color-mix(in srgb, var(--color-text) 55%, transparent)", marginBottom: 6 }}>Content Pillars</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {profile.content_pillars.map((p) => (
                  <span key={p.name} className="tag tag-accent">
                    {p.name}
                  </span>
                ))}
              </div>
            </div>
            <div style={{ marginBottom: "var(--space-3)" }}>
              <div style={{ fontSize: 11, color: "color-mix(in srgb, var(--color-text) 55%, transparent)", marginBottom: 6 }}>Cấm kỵ</div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, opacity: 0.8 }}>
                {profile.forbidden.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            </div>
            <div style={{ marginBottom: "var(--space-4)" }}>
              <div style={{ fontSize: 11, color: "color-mix(in srgb, var(--color-text) 55%, transparent)", marginBottom: 6 }}>Retention Benchmark</div>
              <div style={{ fontSize: 12, opacity: 0.85 }}>
                Hook ≥ {profile.retention_benchmark.target_hook_strength} · Anchor mỗi ≤ {profile.retention_benchmark.max_anchor_gap_sec}s · Body ≥ {profile.retention_benchmark.target_body_len_min} đoạn
              </div>
            </div>
          </>
        )}
        <div className="hr" style={{ margin: "var(--space-2) 0" }} />
        <div style={{ fontSize: 11, color: "color-mix(in srgb, var(--color-text) 55%, transparent)", marginBottom: 6 }}>Phiên bản Pack</div>
        <div style={{ fontSize: 12, opacity: 0.75 }}>{project ? `v${project.pack_version} · hiện hành` : "—"}</div>
      </div>
    </div>
  );
}
