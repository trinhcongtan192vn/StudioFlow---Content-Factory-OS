import { useEffect, useState } from "react";
import { useApp } from "../store/AppContext";
import { api } from "../api/client";
import type { ProjectSummary } from "../api/types";
import { STATUS_DOT_COLOR } from "./statusMeta";
import ChannelDialog from "./ChannelDialog";

export default function Sidebar() {
  const app = useApp();
  const [projectsByChannel, setProjectsByChannel] = useState<Record<string, ProjectSummary[]>>({});
  const [newChannelOpen, setNewChannelOpen] = useState(false);

  useEffect(() => {
    // Refetch mỗi khi 1 kênh được mở HOẶC `projectsVersion` của kênh đó tăng (đổi tên/
    // xoá project ở màn khác gọi app.bumpProjectsVersion để cache ở đây không bị cũ).
    Object.keys(app.expandedChannels).forEach((chId) => {
      if (app.expandedChannels[chId]) {
        api.listProjects(chId).then((ps) => setProjectsByChannel((s) => ({ ...s, [chId]: ps })));
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [app.expandedChannels, app.projectsVersion]);

  // Short-form (2026-08-21) — tự mở rộng project long-form cha khi project ĐANG MỞ là
  // 1 short-form con của nó, để người dùng luôn thấy được vị trí hiện tại trong cây,
  // không cần tự bấm mở rộng thủ công.
  useEffect(() => {
    if (!app.activeProjectId) return;
    for (const projects of Object.values(projectsByChannel)) {
      const active = projects.find((p) => p.id === app.activeProjectId);
      if (active?.parent_project_id) {
        app.expandProject(active.parent_project_id);
        break;
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [app.activeProjectId, projectsByChannel]);

  async function handleNewProject(channelId: string, parentProjectId?: string) {
    const p = await api.createProject(channelId, parentProjectId ? "Short mới chưa có tên" : "Dự án mới chưa có tên", parentProjectId);
    setProjectsByChannel((s) => ({ ...s, [channelId]: [p, ...(s[channelId] || [])] }));
    if (parentProjectId) app.expandProject(parentProjectId);
    app.openProject(channelId, p.id);
  }

  if (app.sidebarCollapsed) {
    return (
      <div style={{ width: 56, flex: "none", display: "flex", flexDirection: "column", borderRight: "1px solid var(--color-divider)", padding: "var(--space-4) var(--space-2)", gap: "var(--space-4)", alignItems: "center" }}>
        <Logo onToggle={app.toggleSidebar} collapsed />
        <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 8, alignItems: "center", paddingTop: 2 }}>
          {app.channels.map((c) => (
            <div
              key={c.id}
              title={c.name}
              onClick={() => app.toggleChannel(c.id)}
              style={{ width: 24, height: 24, borderRadius: 8, background: "var(--color-accent-900)", color: "var(--color-accent-300)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 600, cursor: "pointer", flex: "none" }}
            >
              {c.letter}
            </div>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "center", paddingBottom: 2 }}>
          <div className="hr" style={{ width: 20, margin: "0 auto" }} />
          <NavIcon active={app.view === "dashboard"} onClick={app.goDashboard} title="Dashboard" icon="grid" />
          <NavIcon active={app.view === "asset_vault"} onClick={app.goAssetVault} title="Kho Tài nguyên" icon="vault" />
          <NavIcon active={app.view === "library"} onClick={app.goLibrary} title="Thư viện" icon="library" />
          <NavIcon active={app.view === "trash"} onClick={app.goTrash} title="Thùng rác" icon="trash" />
          <NavIcon active={app.view === "settings"} onClick={app.goSettings} title="Cài đặt" icon="gear" />
        </div>
      </div>
    );
  }

  return (
    <div style={{ width: 240, flex: "none", display: "flex", flexDirection: "column", borderRight: "1px solid var(--color-divider)", padding: "var(--space-4) var(--space-2)", gap: "var(--space-4)", overflow: "hidden" }}>
      <Logo onToggle={app.toggleSidebar} collapsed={false} />

      <div style={{ display: "flex", justifyContent: "flex-end", padding: "0 6px 2px" }}>
        <div
          onClick={() => {
            const allExpanded = app.channels.every((c) => app.expandedChannels[c.id]);
            app.channels.forEach((c) => {
              if (!!app.expandedChannels[c.id] === allExpanded) app.toggleChannel(c.id);
            });
          }}
          style={{ fontSize: 11, color: "var(--color-accent)", cursor: "pointer" }}
        >
          {app.channels.every((c) => app.expandedChannels[c.id]) ? "Thu tất cả" : "Mở tất cả"}
        </div>
      </div>

      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 2 }}>
        {app.channels.map((ch) => {
          const expanded = !!app.expandedChannels[ch.id];
          const projects = projectsByChannel[ch.id] || [];
          return (
            <div key={ch.id}>
              <div
                onClick={() => app.toggleChannel(ch.id)}
                style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 6px", cursor: "pointer", borderRadius: 6 }}
              >
                <Chevron down={expanded} />
                <div style={{ width: 20, height: 20, borderRadius: 6, background: "var(--color-accent-900)", color: "var(--color-accent-300)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 600, flex: "none" }}>{ch.letter}</div>
                <div style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 13 }}>{ch.name}</div>
              </div>
              {expanded && (
                <div style={{ display: "flex", flexDirection: "column", gap: 1, paddingLeft: 30, marginTop: 2 }}>
                  {projects
                    .filter((p) => !p.parent_project_id)
                    .map((p) => {
                      const shorts = projects.filter((c) => c.parent_project_id === p.id);
                      const projectExpanded = !!app.expandedProjects[p.id];
                      return (
                        <div key={p.id}>
                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 4,
                              padding: "5px 6px",
                              cursor: "pointer",
                              borderRadius: 6,
                              fontSize: 12,
                              background: app.activeProjectId === p.id ? "color-mix(in srgb, var(--color-accent) 14%, transparent)" : "transparent",
                              color: app.activeProjectId === p.id ? "var(--color-accent-300)" : "inherit",
                            }}
                          >
                            <div
                              onClick={(e) => {
                                e.stopPropagation();
                                app.toggleProject(p.id);
                              }}
                              style={{ flex: "none", opacity: shorts.length ? 1 : 0.25, cursor: shorts.length ? "pointer" : "default" }}
                              title={shorts.length ? "Short-form thuộc project này" : undefined}
                            >
                              <Chevron down={projectExpanded} />
                            </div>
                            <div
                              onClick={() => app.openProject(ch.id, p.id)}
                              style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 8 }}
                            >
                              <div style={{ width: 6, height: 6, borderRadius: "50%", background: STATUS_DOT_COLOR[p.status] || "var(--color-neutral-600)", flex: "none" }} />
                              <div style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.title}</div>
                            </div>
                          </div>
                          {projectExpanded && (
                            <div style={{ display: "flex", flexDirection: "column", gap: 1, paddingLeft: 20, marginTop: 1 }}>
                              {shorts.map((s) => (
                                <div
                                  key={s.id}
                                  onClick={() => app.openProject(ch.id, s.id)}
                                  style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 6,
                                    padding: "4px 6px",
                                    cursor: "pointer",
                                    borderRadius: 6,
                                    fontSize: 11.5,
                                    background: app.activeProjectId === s.id ? "color-mix(in srgb, var(--color-accent) 14%, transparent)" : "transparent",
                                    color: app.activeProjectId === s.id ? "var(--color-accent-300)" : "inherit",
                                  }}
                                >
                                  <div style={{ width: 5, height: 5, borderRadius: "50%", background: STATUS_DOT_COLOR[s.status] || "var(--color-neutral-600)", flex: "none" }} />
                                  <span className="tag tag-outline" style={{ fontSize: 9, padding: "1px 4px", flex: "none" }}>
                                    9:16
                                  </span>
                                  <div style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.title}</div>
                                </div>
                              ))}
                              <div
                                onClick={() => handleNewProject(ch.id, p.id)}
                                style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 6px", cursor: "pointer", color: "var(--color-accent)", fontSize: 11.5, borderRadius: 6 }}
                              >
                                <PlusIcon size={11} /> Short mới
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  <div
                    onClick={() => handleNewProject(ch.id)}
                    style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 6px", cursor: "pointer", color: "var(--color-accent)", fontSize: 12, borderRadius: 6 }}
                  >
                    <PlusIcon size={12} /> Project mới
                  </div>
                </div>
              )}
            </div>
          );
        })}
        <div
          onClick={() => setNewChannelOpen(true)}
          style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 6px", cursor: "pointer", color: "var(--color-accent)", fontSize: 13, borderRadius: 6, marginTop: 6 }}
        >
          <PlusIcon size={13} /> Kênh mới
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <div className="hr" style={{ margin: "0 0 var(--space-2)" }} />
        <NavRow active={app.view === "dashboard"} onClick={app.goDashboard} label="Dashboard" icon="grid" />
        <NavRow active={app.view === "asset_vault"} onClick={app.goAssetVault} label="Kho Tài nguyên" icon="vault" />
        <NavRow active={app.view === "library"} onClick={app.goLibrary} label="Thư viện" icon="library" />
        <NavRow active={app.view === "trash"} onClick={app.goTrash} label="Thùng rác" icon="trash" />
        <NavRow active={app.view === "settings"} onClick={app.goSettings} label="Cài đặt" icon="gear" />
      </div>

      {newChannelOpen && (
        <ChannelDialog
          mode="create"
          onClose={() => setNewChannelOpen(false)}
          onSaved={async () => {
            await app.refreshChannels();
            setNewChannelOpen(false);
          }}
        />
      )}
    </div>
  );
}

function Logo({ onToggle, collapsed }: { onToggle: () => void; collapsed: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 var(--space-2)" }}>
      <div style={{ width: 26, height: 26, borderRadius: "var(--radius-sm)", border: "1.5px solid var(--color-accent)", display: "flex", alignItems: "center", justifyContent: "center", flex: "none" }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
        </svg>
      </div>
      {!collapsed && (
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: "var(--font-heading)", fontWeight: 600, fontSize: 15, lineHeight: 1.1 }}>StudioFlow</div>
          <div style={{ fontSize: 10, color: "color-mix(in srgb, var(--color-text) 50%, transparent)", letterSpacing: ".03em" }}>CONTENT FACTORY OS</div>
        </div>
      )}
      <svg
        width="13"
        height="13"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        onClick={onToggle}
        style={{ cursor: "pointer", opacity: 0.6, flex: "none", transform: collapsed ? "rotate(180deg)" : "none" }}
      >
        <polyline points="15 18 9 12 15 6" />
      </svg>
    </div>
  );
}

function Chevron({ down }: { down: boolean }) {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: down ? "rotate(90deg)" : "none", transition: "transform .15s" }}>
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

function PlusIcon({ size = 13 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

function NavRow({ active, onClick, label, icon }: { active: boolean; onClick: () => void; label: string; icon: "grid" | "gear" | "trash" | "library" | "vault" }) {
  return (
    <div
      onClick={onClick}
      style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 8px", borderRadius: 6, cursor: "pointer", background: active ? "color-mix(in srgb, var(--color-accent) 14%, transparent)" : "transparent", color: active ? "var(--color-accent-300)" : "inherit" }}
    >
      <IconGlyph icon={icon} />
      <span style={{ fontSize: 13 }}>{label}</span>
    </div>
  );
}

function NavIcon({ active, onClick, title, icon }: { active: boolean; onClick: () => void; title: string; icon: "grid" | "gear" | "trash" | "library" | "vault" }) {
  return (
    <div
      onClick={onClick}
      title={title}
      style={{ width: 26, height: 26, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", background: active ? "color-mix(in srgb, var(--color-accent) 14%, transparent)" : "transparent", color: active ? "var(--color-accent-300)" : "inherit" }}
    >
      <IconGlyph icon={icon} />
    </div>
  );
}

function IconGlyph({ icon }: { icon: "grid" | "gear" | "trash" | "library" | "vault" }) {
  if (icon === "vault")
    return (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="6" width="15" height="12" rx="2" />
        <path d="M17 9.5l5-2.5v10l-5-2.5" />
      </svg>
    );
  if (icon === "library")
    return (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
      </svg>
    );
  if (icon === "grid")
    return (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" />
        <rect x="14" y="3" width="7" height="7" />
        <rect x="14" y="14" width="7" height="7" />
        <rect x="3" y="14" width="7" height="7" />
      </svg>
    );
  if (icon === "trash")
    return (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="3 6 5 6 21 6" />
        <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
        <path d="M10 11v6" />
        <path d="M14 11v6" />
        <path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2" />
      </svg>
    );
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 11-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 110-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 114 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 110 4h-.09a1.65 1.65 0 00-1.51 1z" />
    </svg>
  );
}

