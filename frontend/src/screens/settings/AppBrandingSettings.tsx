import { useEffect, useState } from "react";
import { api } from "../../api/client";

interface AppBranding {
  name: string;
  accent_swatch: number;
}

// Bổ sung ngoài design (§ xem IMPLEMENTATION_REPORT.md "Bổ sung ngoài design") — state
// appBranding/onBrandNameChange/selectBrandSwatch có trong prototype nhưng không có UI.
// Màu workspace ứng dụng (🎨), KHÁC BrandProfile của từng kênh (§06 mục 3).
const SWATCHES = ["#9184d9", "#6ba5d9", "#7fc99a", "#d9a441", "#d97ba0"];

export default function AppBrandingSettings() {
  const [branding, setBranding] = useState<AppBranding | null>(null);

  useEffect(() => {
    api.getSettings().then((s) => setBranding(s.app_branding as unknown as AppBranding));
  }, []);

  useEffect(() => {
    if (branding) document.documentElement.style.setProperty("--color-accent", SWATCHES[branding.accent_swatch] || SWATCHES[0]);
    return () => {
      document.documentElement.style.removeProperty("--color-accent");
    };
  }, [branding?.accent_swatch]);

  function save(patch: Partial<AppBranding>) {
    if (!branding) return;
    const next = { ...branding, ...patch };
    setBranding(next);
    api.putSettings({ app_branding: next });
  }

  if (!branding) return <div style={{ opacity: 0.6 }}>Đang tải...</div>;

  return (
    <div>
      <h3 style={{ marginBottom: 2 }}>Thương hiệu ứng dụng</h3>
      <p style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 13, marginBottom: "var(--space-6)" }}>
        Tên hiển thị &amp; màu chủ đạo của workspace nội bộ — khác BrandProfile của từng kênh.
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)", maxWidth: 420 }}>
        <div className="field">
          <label>Tên tổ chức hiển thị trong app</label>
          <input className="input" type="text" value={branding.name} onChange={(e) => save({ name: e.target.value })} />
        </div>
        <div className="field">
          <label>Màu chủ đạo workspace</label>
          <div style={{ display: "flex", gap: 8 }}>
            {SWATCHES.map((hex, i) => (
              <div
                key={hex}
                onClick={() => save({ accent_swatch: i })}
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: "50%",
                  background: hex,
                  cursor: "pointer",
                  boxShadow: branding.accent_swatch === i ? "0 0 0 2px var(--color-bg), 0 0 0 4px " + hex : "none",
                }}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
