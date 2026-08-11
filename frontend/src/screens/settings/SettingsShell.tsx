import { useState } from "react";
import GeneralSettings from "./GeneralSettings";
import ProviderSettings from "./ProviderSettings";
import BillingSettings from "./BillingSettings";
import AIParamsSettings from "./AIParamsSettings";
import PromptTemplatesSettings from "./PromptTemplatesSettings";
import AuditLogSettings from "./AuditLogSettings";
import AppBrandingSettings from "./AppBrandingSettings";

const NAV = [
  { key: "general", label: "Cấu hình chung" },
  { key: "provider", label: "Provider AI" },
  { key: "billing", label: "Chi phí & Ngân sách" },
  { key: "params", label: "Tham số AI mặc định" },
  { key: "prompts", label: "Prompt Templates" },
  { key: "audit", label: "Audit Log" },
  { key: "branding", label: "Thương hiệu ứng dụng" },
] as const;
type Tab = (typeof NAV)[number]["key"];

export default function SettingsShell() {
  const [tab, setTab] = useState<Tab>("provider");

  return (
    <div style={{ flex: 1, display: "flex", overflow: "hidden", background: "var(--color-neutral-900)" }}>
      <div style={{ width: 210, flex: "none", borderRight: "1px solid var(--color-divider)", padding: "var(--space-4) var(--space-3)", display: "flex", flexDirection: "column", gap: 2 }}>
        <div style={{ fontSize: 11, letterSpacing: ".08em", textTransform: "uppercase", color: "color-mix(in srgb, var(--color-text) 55%, transparent)", padding: "0 var(--space-2)", marginBottom: "var(--space-2)" }}>Phòng máy</div>
        {NAV.map((n) => (
          <div
            key={n.key}
            onClick={() => setTab(n.key)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "7px 8px",
              borderRadius: 6,
              fontSize: 13,
              cursor: "pointer",
              background: tab === n.key ? "color-mix(in srgb, var(--color-accent) 14%, transparent)" : "transparent",
              color: tab === n.key ? "var(--color-accent-300)" : "inherit",
            }}
          >
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor", opacity: 0.5, flex: "none" }} />
            <span style={{ flex: 1 }}>{n.label}</span>
          </div>
        ))}
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-6)" }}>
        {tab === "general" && <GeneralSettings />}
        {tab === "provider" && <ProviderSettings />}
        {tab === "billing" && <BillingSettings />}
        {tab === "params" && <AIParamsSettings />}
        {tab === "prompts" && <PromptTemplatesSettings />}
        {tab === "audit" && <AuditLogSettings />}
        {tab === "branding" && <AppBrandingSettings />}
      </div>
    </div>
  );
}
