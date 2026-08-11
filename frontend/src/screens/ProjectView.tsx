import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { ProductionPack, ProjectSummary } from "../api/types";
import RightPanel from "../components/RightPanel";
import Stepper from "../components/Stepper";
import { useApp } from "../store/AppContext";
import BriefEditor from "./steps/BriefEditor";
import Gate1Outline from "./steps/Gate1Outline";
import ScriptStudio from "./steps/ScriptStudio";
import VisualStudio from "./steps/VisualStudio";
import PackReview from "./steps/PackReview";
import OutputCenter from "./steps/OutputCenter";

export interface StepProps {
  project: ProjectSummary;
  pack: ProductionPack;
  refresh: () => Promise<void>;
  setBusy: (b: boolean) => void;
  busy: boolean;
}

export default function ProjectView() {
  const app = useApp();
  const projectId = app.activeProjectId!;
  const [project, setProject] = useState<ProjectSummary | null>(null);
  const [pack, setPack] = useState<ProductionPack | null>(null);
  const [busy, setBusy] = useState(false);
  const channelName = app.channels.find((c) => c.id === app.activeChannelId)?.name || "";

  const refresh = useCallback(async () => {
    const [p, pk] = await Promise.all([api.getProject(projectId), api.getPack(projectId)]);
    setProject(p);
    setPack(pk);
  }, [projectId]);

  useEffect(() => {
    setProject(null);
    setPack(null);
    refresh();
  }, [refresh]);

  async function jumpStep(i: number) {
    if (!project) return;
    const updated = await api.patchProject(project.id, { step: i });
    setProject(updated);
  }

  if (!project || !pack) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", opacity: 0.6 }}>Đang tải...</div>
    );
  }

  const stepProps: StepProps = { project, pack, refresh, setBusy, busy };

  return (
    <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ padding: "var(--space-3) var(--space-6)", borderBottom: "1px solid var(--color-divider)", display: "flex", alignItems: "center", gap: "var(--space-3)", flex: "none" }}>
        <div onClick={app.goDashboard} style={{ display: "flex", alignItems: "center", gap: 5, cursor: "pointer", color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 12 }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </svg>
          Dashboard
        </div>
        <span style={{ color: "color-mix(in srgb, var(--color-text) 30%, transparent)" }}>/</span>
        <div style={{ fontSize: 13, color: "color-mix(in srgb, var(--color-text) 60%, transparent)" }}>{channelName}</div>
        <span style={{ color: "color-mix(in srgb, var(--color-text) 30%, transparent)" }}>/</span>
        <div style={{ fontFamily: "var(--font-heading)", fontWeight: 600, fontSize: 14 }}>{project.title}</div>
      </div>

      <Stepper step={project.step} maxStepReached={project.max_step_reached} onJump={jumpStep} />

      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-6)", minWidth: 0 }}>
          {project.step === 0 && <BriefEditor {...stepProps} />}
          {project.step === 1 && <Gate1Outline {...stepProps} />}
          {project.step === 2 && <ScriptStudio {...stepProps} />}
          {project.step === 3 && <VisualStudio {...stepProps} />}
          {project.step === 4 && <PackReview {...stepProps} />}
          {project.step === 5 && <OutputCenter {...stepProps} />}
        </div>
        <RightPanel channelId={project.channel_id} project={project} />
      </div>
    </div>
  );
}
