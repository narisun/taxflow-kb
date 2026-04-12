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
        "bg-[#f5f5f7] rounded-lg p-4",
        elevated && "shadow-[3px_5px_30px_rgba(0,0,0,0.22)]",
        className
      )}
    >
      {children}
    </div>
  );
}

export { Card, type CardProps };
