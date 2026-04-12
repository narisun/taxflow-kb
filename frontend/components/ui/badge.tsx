import { cn } from "@/lib/utils";

type BadgeVariant = "pending" | "inProgress" | "review" | "completed" | "filed";

interface BadgeProps {
  variant: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

const variantClasses: Record<BadgeVariant, string> = {
  pending: "bg-badge-pending-bg text-badge-pending-text",
  inProgress: "bg-badge-progress-bg text-badge-progress-text",
  review: "bg-badge-review-bg text-badge-review-text",
  completed: "bg-badge-complete-bg text-badge-complete-text",
  filed: "bg-badge-filed-bg text-badge-filed-text",
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
