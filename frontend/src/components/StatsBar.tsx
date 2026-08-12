import type { PackStats } from "./packStats";

export default function StatsBar({ wordCount, shotCount, durationLabel }: PackStats) {
  return (
    <span style={{ display: "inline-block", marginLeft: 8, opacity: 0.75, fontSize: 12 }}>
      {wordCount} từ · {shotCount} shot · {durationLabel}
    </span>
  );
}
