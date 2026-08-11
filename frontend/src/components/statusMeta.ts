export const STATUS_LABEL: Record<string, string> = {
  draft: "Draft",
  researching: "Đang nghiên cứu",
  await_gate1: "Chờ Gate 1",
  generating: "Đang viết",
  await_gate2: "Chờ Gate 2",
  ready_output: "Sẵn sàng Output",
  exported: "Đã export",
  published: "Đã đăng",
};

export const STATUS_DOT_COLOR: Record<string, string> = {
  draft: "var(--color-neutral-600)",
  researching: "var(--color-accent-400)",
  await_gate1: "var(--color-accent-400)",
  generating: "var(--color-accent-500)",
  await_gate2: "var(--color-accent-600)",
  ready_output: "var(--color-accent)",
  exported: "var(--color-accent)",
  published: "var(--color-accent)",
};

export const STEP_LABELS = ["Brief", "Outline & Hook", "Script Studio", "Visual Studio", "Pack Review", "Output"];
