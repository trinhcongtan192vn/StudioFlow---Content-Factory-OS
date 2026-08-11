import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { BrandProfile } from "../api/types";

interface Draft {
  name: string;
  niche: string;
  tone: string;
  pacing: string;
  pillarsText: string;
  taboosText: string;
  targetHookStrength: string;
  maxAnchorGapSec: string;
  targetBodyLenMin: string;
  visualStylePrompt: string;
}

function emptyDraft(): Draft {
  return {
    name: "",
    niche: "",
    tone: "",
    pacing: "",
    pillarsText: "",
    taboosText: "",
    targetHookStrength: "0.7",
    maxAnchorGapSec: "45",
    targetBodyLenMin: "8",
    visualStylePrompt: "",
  };
}

function draftFromProfile(name: string, niche: string, bp: BrandProfile): Draft {
  return {
    name,
    niche,
    tone: bp.brand_voice?.tone || "",
    pacing: bp.brand_voice?.pacing || "",
    pillarsText: (bp.content_pillars || []).map((p) => p.name).join(", "),
    taboosText: (bp.forbidden || []).join(", "),
    targetHookStrength: String(bp.retention_benchmark?.target_hook_strength ?? 0.7),
    maxAnchorGapSec: String(bp.retention_benchmark?.max_anchor_gap_sec ?? 45),
    targetBodyLenMin: String(bp.retention_benchmark?.target_body_len_min ?? 8),
    visualStylePrompt: bp.visual_style_prompt || "",
  };
}

export default function ChannelDialog({ mode, channelId, onClose, onSaved }: { mode: "create" | "edit"; channelId?: string; onClose: () => void; onSaved: () => void }) {
  const [draft, setDraft] = useState<Draft>(emptyDraft());
  const [loading, setLoading] = useState(mode === "edit");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (mode === "edit" && channelId) {
      api.getChannel(channelId).then((ch) => {
        setDraft(draftFromProfile(ch.name, ch.niche, ch.brand_profile));
        setLoading(false);
      });
    }
  }, [mode, channelId]);

  function set<K extends keyof Draft>(k: K, v: Draft[K]) {
    setDraft((d) => ({ ...d, [k]: v }));
  }

  async function save() {
    if (!draft.name.trim()) return;
    setSaving(true);
    try {
      const pillars = draft.pillarsText.split(",").map((s) => s.trim()).filter(Boolean);
      const taboos = draft.taboosText.split(",").map((s) => s.trim()).filter(Boolean);

      let id = channelId;
      if (mode === "create") {
        const ch = await api.createChannel({ name: draft.name.trim(), niche: draft.niche.trim() });
        id = ch.id;
      } else {
        await api.patchChannel(id!, { name: draft.name.trim(), niche: draft.niche.trim() });
      }

      const current = await api.getBrandProfile(id!);
      const nextProfile: BrandProfile = {
        ...current,
        niche: draft.niche.trim(),
        brand_voice: { ...current.brand_voice, tone: draft.tone, pacing: draft.pacing },
        content_pillars: pillars.map((name) => ({ name, weight: pillars.length ? Math.round((1 / pillars.length) * 100) / 100 : 0 })),
        forbidden: taboos,
        visual_style_prompt: draft.visualStylePrompt,
        retention_benchmark: {
          target_hook_strength: parseFloat(draft.targetHookStrength) || 0.7,
          max_anchor_gap_sec: parseInt(draft.maxAnchorGapSec) || 45,
          target_body_len_min: parseInt(draft.targetBodyLenMin) || 8,
        },
      };
      await api.putBrandProfile(id!, nextProfile);
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" style={{ width: "min(520px,100%)", maxHeight: "88vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <div className="dialog-title">{mode === "create" ? "Tạo kênh mới" : "Sửa BrandProfile"}</div>
        {loading ? (
          <div style={{ opacity: 0.6, fontSize: 13 }}>Đang tải...</div>
        ) : (
          <>
            <div className="field">
              <label>Tên kênh</label>
              <input className="input" value={draft.name} onChange={(e) => set("name", e.target.value)} placeholder="VD: Sử Việt Kể" />
            </div>
            <div className="field">
              <label>Thể loại (niche)</label>
              <input className="input" value={draft.niche} onChange={(e) => set("niche", e.target.value)} placeholder="VD: Lịch sử" />
            </div>
            <div className="field">
              <label>Tông giọng (brand voice)</label>
              <textarea className="input" rows={2} value={draft.tone} onChange={(e) => set("tone", e.target.value)} placeholder="VD: Trầm, kể chuyện, nhiều chi tiết cảm xúc" />
            </div>
            <div className="field">
              <label>Nhịp điệu</label>
              <input className="input" value={draft.pacing} onChange={(e) => set("pacing", e.target.value)} placeholder="VD: chậm, giàu hình ảnh" />
            </div>
            <div className="field">
              <label>Content pillars (phân tách bằng dấu phẩy)</label>
              <input className="input" value={draft.pillarsText} onChange={(e) => set("pillarsText", e.target.value)} placeholder="Nhân vật lịch sử, Bí ẩn chưa giải" />
            </div>
            <div className="field">
              <label>Danh sách cấm kỵ (phân tách bằng dấu phẩy)</label>
              <input className="input" value={draft.taboosText} onChange={(e) => set("taboosText", e.target.value)} placeholder="Xuyên tạc chính sử" />
            </div>
            <div className="field">
              <label>Style hình ảnh (visual_style_prompt)</label>
              <input className="input" value={draft.visualStylePrompt} onChange={(e) => set("visualStylePrompt", e.target.value)} placeholder="archival tone, muted sepia" />
            </div>
            <div className="field">
              <label>Retention Benchmark</label>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
                <div>
                  <label style={{ fontSize: 11 }}>Hook Strength (0-1)</label>
                  <input className="input" type="number" min={0} max={1} step={0.05} value={draft.targetHookStrength} onChange={(e) => set("targetHookStrength", e.target.value)} />
                </div>
                <div>
                  <label style={{ fontSize: 11 }}>Anchor gap (giây)</label>
                  <input className="input" type="number" min={5} value={draft.maxAnchorGapSec} onChange={(e) => set("maxAnchorGapSec", e.target.value)} />
                </div>
                <div>
                  <label style={{ fontSize: 11 }}>Body tối thiểu (đoạn)</label>
                  <input className="input" type="number" min={1} value={draft.targetBodyLenMin} onChange={(e) => set("targetBodyLenMin", e.target.value)} />
                </div>
              </div>
            </div>
          </>
        )}
        <div className="dialog-actions">
          <button className="btn btn-secondary" onClick={onClose}>
            Hủy
          </button>
          <button className="btn btn-primary" disabled={!draft.name.trim() || saving || loading} onClick={save}>
            {saving ? "Đang lưu..." : mode === "create" ? "Tạo kênh" : "Lưu thay đổi"}
          </button>
        </div>
      </div>
    </div>
  );
}
