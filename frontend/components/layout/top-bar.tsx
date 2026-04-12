import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";

interface TopBarProps {
  stats: { clients: number; filed: number; review: number };
  deadline: string;
  user: { initials: string; name?: string };
}

function TopBar({ stats, deadline, user }: TopBarProps) {
  return (
    <nav
      className="h-12 flex items-center px-4 gap-4 shrink-0 z-50"
      style={{
        background: "rgba(0, 0, 0, 0.8)",
        backdropFilter: "saturate(180%) blur(20px)",
      }}
    >
      {/* Logo */}
      <div className="flex items-center gap-2">
        <div className="w-7 h-7 bg-[#0071e3] rounded-md flex items-center justify-center text-white text-[13px] font-bold">
          T
        </div>
        <span className="text-white text-[14px] font-semibold tracking-tight">
          TaxFlow AI
        </span>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Stats */}
      <div className="flex items-center gap-4 text-[12px] text-white/70">
        <span>
          <span className="text-white font-medium">{stats.clients}</span> clients
        </span>
        <span>
          <span className="text-green-400 font-medium">{stats.filed}</span> filed
        </span>
        <span>
          <span className="text-orange-400 font-medium">{stats.review}</span> review
        </span>
      </div>

      <div className="w-px h-5 bg-white/20" />

      {/* Deadline */}
      <div className="text-[12px] text-red-400 font-medium">{deadline}</div>

      {/* User avatar */}
      <Avatar initials={user.initials} size="sm" color="#6B7280" />
    </nav>
  );
}

export { TopBar, type TopBarProps };
