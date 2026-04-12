import { cn } from "@/lib/utils";

interface CardProps {
  elevated?: boolean;
  children: React.ReactNode;
  className?: string;
}

function Card({ elevated = false, children, className }: CardProps) {
  return (
    <div
      className={cn(
        "bg-surface-secondary rounded-xl p-4",
        elevated && "shadow-lg",
        className
      )}
    >
      {children}
    </div>
  );
}

export { Card, type CardProps };
