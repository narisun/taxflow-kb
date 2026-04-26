import { cn } from "@/lib/utils";

type AvatarSize = "sm" | "md" | "lg";

interface AvatarProps {
  initials: string;
  color?: string;
  size?: AvatarSize;
  className?: string;
}

const sizeClasses: Record<AvatarSize, string> = {
  sm: "w-6 h-6 text-[10px]",
  md: "w-8 h-8 text-[13px]",
  lg: "w-10 h-10 text-[15px]",
};

function Avatar({ initials, color = "#0071e3", size = "md", className }: AvatarProps) {
  return (
    <div
      className={cn(
        "rounded-full flex items-center justify-center font-bold text-white shrink-0",
        sizeClasses[size],
        className
      )}
      style={{ backgroundColor: color }}
    >
      {initials}
    </div>
  );
}

export { Avatar, type AvatarProps, type AvatarSize };
