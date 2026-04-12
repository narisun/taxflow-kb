import { cn } from "@/lib/utils";

type ProgressColor = "blue" | "green" | "orange" | "red";

interface ProgressProps {
  value: number;
  color?: ProgressColor;
  className?: string;
}

const colorClasses: Record<ProgressColor, string> = {
  blue: "bg-[#0071e3]",
  green: "bg-green-500",
  orange: "bg-orange-500",
  red: "bg-red-500",
};

function Progress({ value, color = "blue", className }: ProgressProps) {
  const clampedValue = Math.min(100, Math.max(0, value));

  return (
    <div className={cn("h-1 bg-gray-200 rounded-full overflow-hidden", className)}>
      <div
        className={cn("h-full rounded-full transition-all", colorClasses[color])}
        style={{ width: `${clampedValue}%` }}
      />
    </div>
  );
}

export { Progress, type ProgressProps, type ProgressColor };
