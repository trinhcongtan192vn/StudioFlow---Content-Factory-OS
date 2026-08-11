import { useEffect, useState } from "react";
import { api } from "../../api/client";

interface General {
  org_name: string;
  language: string;
  timezone: string;
  export_format: string;
  naming_convention: string;
}

export default function GeneralSettings() {
  const [general, setGeneral] = useState<General | null>(null);

  useEffect(() => {
    api.getSettings().then((s) => setGeneral(s.general as unknown as General));
  }, []);

  function save(patch: Partial<General>) {
    if (!general) return;
    const next = { ...general, ...patch };
    setGeneral(next);
    api.putSettings({ general: next });
  }

  if (!general) return <div style={{ opacity: 0.6 }}>Đang tải...</div>;

  return (
    <div>
      <h3 style={{ marginBottom: "var(--space-4)" }}>Cấu hình chung</h3>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", maxWidth: 420 }}>
        <div className="field">
          <label>Tên tổ chức</label>
          <input className="input" type="text" value={general.org_name} onChange={(e) => save({ org_name: e.target.value })} />
        </div>
        <div className="field">
          <label>Ngôn ngữ mặc định</label>
          <div className="seg">
            <label className="seg-opt">
              <input type="radio" checked={general.language === "vi"} onChange={() => save({ language: "vi" })} />
              Tiếng Việt
            </label>
            <label className="seg-opt">
              <input type="radio" checked={general.language === "en"} onChange={() => save({ language: "en" })} />
              English
            </label>
          </div>
        </div>
        <div className="field">
          <label>Múi giờ</label>
          <input className="input" type="text" value={general.timezone} readOnly />
        </div>
        <div className="field">
          <label>Định dạng export mặc định</label>
          <div className="seg">
            {["markdown", "pdf", "json"].map((f) => (
              <label key={f} className="seg-opt">
                <input type="radio" checked={general.export_format === f} onChange={() => save({ export_format: f })} />
                {f}
              </label>
            ))}
          </div>
        </div>
        <div className="field">
          <label>Quy ước đặt tên Project</label>
          <input className="input" type="text" value={general.naming_convention} onChange={(e) => save({ naming_convention: e.target.value })} />
        </div>
      </div>
    </div>
  );
}
