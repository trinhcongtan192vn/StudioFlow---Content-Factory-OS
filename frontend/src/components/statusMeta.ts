// "researching"/"await_gate1"/"await_gate2" đã bỏ (2026-08-17, mục 44
// IMPLEMENTATION_REPORT.md) cùng lúc bỏ AI Research/Outline/Hook + Pack Review/Gate #2.
export const STATUS_LABEL: Record<string, string> = {
  draft: "Draft",
  generating: "Đang viết",
  ready_output: "Sẵn sàng Output",
  exported: "Đã export",
  published: "Đã đăng",
};

export const STATUS_DOT_COLOR: Record<string, string> = {
  draft: "var(--color-neutral-600)",
  generating: "var(--color-accent-500)",
  ready_output: "var(--color-accent)",
  exported: "var(--color-accent)",
  published: "var(--color-accent)",
};

export const STEP_LABELS = ["Brief", "Script Studio", "Visual Studio", "Output"];
