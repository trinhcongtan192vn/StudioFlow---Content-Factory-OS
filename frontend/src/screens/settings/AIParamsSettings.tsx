import { useEffect, useState } from "react";
import { api } from "../../api/client";

interface AIParams {
  temperature: number;
  length: string;
  hook_count: number;
  framework: string;
}

const LENGTH_OPTIONS = ["1-3 phút", "3-6 phút", "6-10 phút", "10+ phút"];
const FRAMEWORK_OPTIONS = ["AIDA", "PAS"];

export default function AIParamsSettings() {
  const [params, setParams] = useState<AIParams | null>(null);

  useEffect(() => {
    api.getSettings().then((s) => setParams(s.ai_params as unknown as AIParams));
  }, []);

  function save(patch: Partial<AIParams>) {
    if (!params) return;
    const next = { ...params, ...patch };
    setParams(next);
    api.putSettings({ ai_params: next });
  }

  if (!params) return <div style={{ opacity: 0.6 }}>Đang tải...</div>;

  return (
    <div>
      <h3 style={{ marginBottom: 2 }}>Tham số AI mặc định</h3>
      <p style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 13, marginBottom: "var(--space-6)" }}>Mặc định cấp hệ thống — từng kênh có thể override.</p>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)", maxWidth: 440 }}>
        <div className="field">
          <label>Temperature — {params.temperature.toFixed(2)}</label>
          <input type="range" min={0} max={1} step={0.05} value={params.temperature} onChange={(e) => save({ temperature: parseFloat(e.target.value) })} style={{ width: "100%", accentColor: "var(--color-accent)" }} />
        </div>
        <div className="field">
          <label>Độ dài kịch bản mặc định</label>
          <div className="seg">
            {LENGTH_OPTIONS.map((l) => (
              <label key={l} className="seg-opt">
                <input type="radio" checked={params.length === l} onChange={() => save({ length: l })} />
                {l}
              </label>
            ))}
          </div>
        </div>
        <div className="field">
          <label>Số Hook variant mặc định — {params.hook_count}</label>
          <input type="range" min={1} max={5} step={1} value={params.hook_count} onChange={(e) => save({ hook_count: parseInt(e.target.value) })} style={{ width: "100%", accentColor: "var(--color-accent)" }} />
        </div>
        <div className="field">
          <label>Framework ưu tiên</label>
          <div className="seg">
            {FRAMEWORK_OPTIONS.map((f) => (
              <label key={f} className="seg-opt">
                <input type="radio" checked={params.framework === f} onChange={() => save({ framework: f })} />
                {f}
              </label>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
