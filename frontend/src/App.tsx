import Sidebar from "./components/Sidebar";
import Dashboard from "./screens/Dashboard";
import ProjectView from "./screens/ProjectView";
import SettingsShell from "./screens/settings/SettingsShell";
import { AppProvider, useApp } from "./store/AppContext";

function Shell() {
  const app = useApp();
  return (
    <div style={{ display: "flex", height: "100vh", background: "var(--color-bg)", color: "var(--color-text)", fontFamily: "var(--font-body)", overflow: "hidden", fontSize: 14 }}>
      <Sidebar />
      {app.view === "dashboard" && <Dashboard />}
      {app.view === "project" && app.activeProjectId && <ProjectView />}
      {app.view === "settings" && <SettingsShell />}
      {!app.hasLlmProvider && app.view !== "settings" && (
        <div style={{ position: "fixed", bottom: 16, right: 16, maxWidth: 320, zIndex: 50 }}>
          <div className="card elev-md" style={{ gap: 8 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-warning)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flex: "none", marginTop: 1 }}>
                <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <div style={{ fontSize: 13 }}>Cần cấu hình Provider AI để chạy tuyến sản xuất.</div>
            </div>
            <button className="btn btn-primary" style={{ fontSize: 12 }} onClick={app.goSettings}>
              Cấu hình ngay →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}
