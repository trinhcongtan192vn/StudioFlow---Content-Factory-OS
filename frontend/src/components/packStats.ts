import type { ProductionPack, RenderState } from "../api/types";

/** "125" -> "2:05", "3725" -> "1:02:05". */
export function formatDuration(totalSec: number): string {
  const s = Math.round(totalSec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
}

export interface PackStats {
  wordCount: number;
  shotCount: number;
  durationLabel: string;
}

/** Thống kê ước tính từ kịch bản — dùng ở Script Studio & Visual Studio (thời lượng
 * suy ra từ end_sec xa nhất trong body, KHÔNG PHẢI thời lượng giọng đọc thật). */
export function computeEstimatedStats(pack: ProductionPack): PackStats {
  const body = pack.script?.body || [];
  const wordCount = (pack.script?.full_text || body.map((b) => b.audio).join(" ")).split(/\s+/).filter(Boolean).length;
  const shotCount = pack.shots.length || body.length;
  const maxEnd = body.reduce((m, b) => Math.max(m, b.end_sec ?? b.timestamp_sec ?? 0), 0);
  return { wordCount, shotCount, durationLabel: maxEnd > 0 ? formatDuration(maxEnd) : "—" };
}

/** Thống kê ở Pack Review — thời lượng là THẬT, cộng dồn từ độ dài file giọng đọc đã
 * sinh (narration_duration_sec, đo qua ffprobe — xem backend app/render/engine.py).
 * Shot nào chưa sinh giọng đọc thì chưa cộng vào — tổng chỉ phản ánh phần đã có. */
export function computeRealStats(pack: ProductionPack, renderState: RenderState | null): PackStats {
  const body = pack.script?.body || [];
  const wordCount = (pack.script?.full_text || body.map((b) => b.audio).join(" ")).split(/\s+/).filter(Boolean).length;
  const shotCount = pack.shots.length || body.length;
  const readyDurations = (renderState?.shots || []).filter((s) => s.narration_status === "ready" && s.narration_duration_sec != null);
  const totalSec = readyDurations.reduce((sum, s) => sum + (s.narration_duration_sec || 0), 0);
  const allReady = readyDurations.length > 0 && readyDurations.length === (renderState?.shots.length || 0);
  const durationLabel = totalSec > 0 ? `${formatDuration(totalSec)}${allReady ? "" : " (một phần)"}` : "—";
  return { wordCount, shotCount, durationLabel };
}
