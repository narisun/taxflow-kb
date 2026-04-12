import { cn } from "@/lib/utils";

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div className={cn("bg-surface-tertiary rounded-lg animate-skeleton", className)} />
  );
}

export function ChatSkeleton() {
  return (
    <div className="space-y-4 px-5 py-4">
      <div className="flex gap-2.5">
        <Skeleton className="w-7 h-7 rounded-md shrink-0" />
        <Skeleton className="h-16 w-[60%] rounded-2xl" />
      </div>
      <div className="flex gap-2.5 justify-end">
        <Skeleton className="h-10 w-[45%] rounded-2xl" />
        <Skeleton className="w-7 h-7 rounded-md shrink-0" />
      </div>
      <div className="flex gap-2.5">
        <Skeleton className="w-7 h-7 rounded-md shrink-0" />
        <Skeleton className="h-20 w-[55%] rounded-2xl" />
      </div>
    </div>
  );
}

export function ClientListSkeleton() {
  return (
    <div className="space-y-1 p-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="flex items-center gap-2.5 px-3 py-2.5">
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-[70%]" />
            <Skeleton className="h-2.5 w-[50%]" />
          </div>
          <Skeleton className="h-5 w-14 rounded-full" />
        </div>
      ))}
    </div>
  );
}

export function MetricCardSkeleton() {
  return (
    <div className="bg-surface-secondary rounded-xl p-5 space-y-2">
      <Skeleton className="h-8 w-16 mx-auto" />
      <Skeleton className="h-3 w-20 mx-auto" />
    </div>
  );
}
