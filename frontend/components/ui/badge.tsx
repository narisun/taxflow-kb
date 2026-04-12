import { cn } from "@/lib/utils";

type BadgeVariant = "pending" | "inProgress" | "review" | "completed" | "filed";

interface BadgeProps {
  variant: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

const variantClasses: Record<BadgeVariant, string> = {
  pending: "bg-gray-200 text-gray-600",
  inProgress: "bg-blue-100 text-blue-700",
  review: "bg-orange-100 text-orange-700",
  completed: "bg-green-100 text-green-700",
  filed: "bg-purple-100 text-purple-700",
};

function Badge({ variant, children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        "text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full inline-block",
        variantClasses[variant],
        className
      )}
    >
      {children}
    </span>
  );
}

export { Badge, type BadgeProps, type BadgeVariant };
