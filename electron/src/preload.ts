// Preload — truyền cổng backend cho renderer qua window.STUDIOFLOW_API_BASE (§01).
import { contextBridge } from "electron";

const port = process.env.STUDIOFLOW_API_PORT || "8756";

contextBridge.exposeInMainWorld("STUDIOFLOW_API_BASE", `http://127.0.0.1:${port}`);
