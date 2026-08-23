import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "../api/client";
import type { ChannelSummary } from "../api/types";

type View = "dashboard" | "project" | "settings" | "trash" | "library";

interface AppState {
  view: View;
  channels: ChannelSummary[];
  activeChannelId: string | null;
  activeProjectId: string | null;
  sidebarCollapsed: boolean;
  rightPanelOpen: boolean;
  expandedChannels: Record<string, boolean>;
  // Short-form (2026-08-21) — mở rộng danh sách short-form con dưới 1 project long-form
  // trong Sidebar, cùng pattern `expandedChannels` (key = id project long-form).
  expandedProjects: Record<string, boolean>;
  hasLlmProvider: boolean;
  projectsVersion: Record<string, number>;
  goDashboard: () => void;
  goSettings: () => void;
  goTrash: () => void;
  goLibrary: () => void;
  openProject: (channelId: string, projectId: string) => void;
  toggleChannel: (channelId: string) => void;
  toggleProject: (projectId: string) => void;
  expandProject: (projectId: string) => void;
  toggleSidebar: () => void;
  toggleRightPanel: () => void;
  refreshChannels: () => Promise<void>;
  refreshBootstrap: () => Promise<void>;
  bumpProjectsVersion: (channelId: string) => void;
}

const AppCtx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [view, setView] = useState<View>("dashboard");
  const [channels, setChannels] = useState<ChannelSummary[]>([]);
  const [activeChannelId, setActiveChannelId] = useState<string | null>(null);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [expandedChannels, setExpandedChannels] = useState<Record<string, boolean>>({});
  const [expandedProjects, setExpandedProjects] = useState<Record<string, boolean>>({});
  const [hasLlmProvider, setHasLlmProvider] = useState(true);
  const [projectsVersion, setProjectsVersion] = useState<Record<string, number>>({});

  const refreshChannels = useCallback(async () => {
    const list = await api.listChannels();
    setChannels(list);
  }, []);

  const refreshBootstrap = useCallback(async () => {
    const b = await api.bootstrap();
    setHasLlmProvider(b.has_llm_provider);
  }, []);

  useEffect(() => {
    refreshChannels();
    refreshBootstrap();
  }, [refreshChannels, refreshBootstrap]);

  const goDashboard = () => {
    setView("dashboard");
    setActiveProjectId(null);
  };
  const goSettings = () => setView("settings");
  const goTrash = () => setView("trash");
  const goLibrary = () => setView("library");
  const openProject = (channelId: string, projectId: string) => {
    setActiveChannelId(channelId);
    setActiveProjectId(projectId);
    setView("project");
    setExpandedChannels((s) => ({ ...s, [channelId]: true }));
  };
  const toggleChannel = (channelId: string) => setExpandedChannels((s) => ({ ...s, [channelId]: !s[channelId] }));
  const toggleProject = (projectId: string) => setExpandedProjects((s) => ({ ...s, [projectId]: !s[projectId] }));
  const expandProject = (projectId: string) => setExpandedProjects((s) => (s[projectId] ? s : { ...s, [projectId]: true }));
  const toggleSidebar = () => setSidebarCollapsed((s) => !s);
  const toggleRightPanel = () => setRightPanelOpen((s) => !s);
  const bumpProjectsVersion = (channelId: string) => setProjectsVersion((s) => ({ ...s, [channelId]: (s[channelId] || 0) + 1 }));

  const value: AppState = {
    view,
    channels,
    activeChannelId,
    activeProjectId,
    sidebarCollapsed,
    rightPanelOpen,
    expandedChannels,
    expandedProjects,
    hasLlmProvider,
    projectsVersion,
    goDashboard,
    goSettings,
    goTrash,
    goLibrary,
    openProject,
    toggleChannel,
    toggleProject,
    expandProject,
    toggleSidebar,
    toggleRightPanel,
    refreshChannels,
    refreshBootstrap,
    bumpProjectsVersion,
  };
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(AppCtx);
  if (!ctx) throw new Error("useApp phải dùng trong AppProvider");
  return ctx;
}
