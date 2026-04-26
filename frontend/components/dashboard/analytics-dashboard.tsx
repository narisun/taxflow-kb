// frontend/components/dashboard/analytics-dashboard.tsx
"use client";

import { useMemo } from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Client } from "@/lib/api-client";

interface AnalyticsDashboardProps {
  clients: Client[];
}

const STEP_ORDER = ["intake", "documents", "tax_return", "review", "filed"] as const;

const stepMeta: Record<string, { label: string; badge: "pending" | "inProgress" | "review" | "completed" | "filed"; color: string }> = {
  intake:     { label: "Intake",     badge: "pending",     color: "bg-badge-pending-bg" },
  documents:  { label: "Documents",  badge: "inProgress",  color: "bg-badge-progress-bg" },
  tax_return: { label: "Tax Return", badge: "review",      color: "bg-badge-review-bg" },
  review:     { label: "Review",     badge: "completed",   color: "bg-badge-complete-bg" },
  filed:      { label: "Filed",      badge: "filed",       color: "bg-badge-filed-bg" },
};

const deadlines = [
  { date: "Apr 15, 2026", desc: "Individual returns", accent: "text-red-500" },
  { date: "Jun 15, 2026", desc: "Estimated Q2 payments", accent: "text-orange-500" },
  { date: "Sep 15, 2026", desc: "Extension deadline", accent: "text-yellow-600 dark:text-yellow-400" },
  { date: "Jan 15, 2027", desc: "Estimated Q4 payments", accent: "text-tertiary" },
];

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export function AnalyticsDashboard({ clients }: AnalyticsDashboardProps) {
  const stats = useMemo(() => {
    const total = clients.length;
    const stepCounts: Record<string, number> = {};
    for (const s of STEP_ORDER) stepCounts[s] = 0;
    for (const c of clients) {
      const step = c.workflow_step || "intake";
      stepCounts[step] = (stepCounts[step] || 0) + 1;
    }

    const filed = stepCounts["filed"] || 0;
    const review = stepCounts["review"] || 0;
    const filedPct = total > 0 ? Math.round((filed / total) * 100) : 0;

    const recentClients = [...clients]
      .filter((c) => c.updated_at || c.created_at)
      .sort((a, b) => new Date(b.updated_at || b.created_at).getTime() - new Date(a.updated_at || a.created_at).getTime())
      .slice(0, 4);

    const activity = recentClients.map((c) => {
      const step = c.workflow_step || "intake";
      const icons: Record<string, string> = { intake: "👤", documents: "📄", tax_return: "📊", review: "🔍", filed: "✅" };
      const labels: Record<string, string> = {
        intake: `${c.name} — intake in progress`,
        documents: `${c.name} — documents under review`,
        tax_return: `${c.name} — return being prepared`,
        review: `${c.name} — ready for review`,
        filed: `${c.name} — return filed`,
      };
      return {
        icon: icons[step] || "📋",
        text: labels[step] || `${c.name} — ${step}`,
        time: timeAgo(c.updated_at || c.created_at),
      };
    });

    const unfiled = clients.filter((c) => c.workflow_step !== "filed");

    return { total, filed, review, filedPct, stepCounts, activity, unfiled: unfiled.length };
  }, [clients]);

  const pipeline = STEP_ORDER.map((step) => ({
    stage: stepMeta[step].label,
    count: stats.stepCounts[step] || 0,
    color: stepMeta[step].color,
    badge: stepMeta[step].badge,
  }));

  const metrics = [
    { label: "Total Clients", value: String(stats.total), trend: `${stats.unfiled} active`, trendUp: true, color: "text-apple-blue" },
    { label: "Returns Filed", value: String(stats.filed), trend: `${stats.filedPct}%`, trendUp: true, color: "text-brand-green" },
    { label: "Pending Review", value: String(stats.review), trend: stats.review > 0 ? `${stats.review} pending` : "All clear", trendUp: stats.review === 0, color: "text-orange-500" },
    { label: "In Progress", value: String(stats.total - stats.filed), trend: `${stats.total - stats.filed} remaining`, trendUp: false, color: "text-apple-blue" },
  ];

  return (
    <div className="p-4 space-y-3">
      {/* Season progress — top */}
      <Card className="p-3">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-[12px] font-semibold text-primary">
            Tax Season {new Date().getFullYear() - 1}
          </h3>
          <span className="text-[11px] text-secondary">{stats.filed} of {stats.total} filed ({stats.filedPct}%)</span>
        </div>
        <div className="h-2.5 rounded-full bg-surface-tertiary overflow-hidden flex">
          <div className="bg-brand-green h-full" style={{ width: `${stats.filedPct}%` }} />
          <div className="bg-orange-500 h-full" style={{ width: `${stats.total > 0 ? (stats.review / stats.total) * 100 : 0}%` }} />
        </div>
        <div className="flex gap-4 mt-1.5 text-[10px]">
          <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-brand-green" /> Filed ({stats.filed})</span>
          <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-orange-500" /> Review ({stats.review})</span>
          <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-surface-tertiary" /> Other ({stats.total - stats.filed - stats.review})</span>
        </div>
      </Card>

      {/* Metric cards */}
      <div className="grid grid-cols-4 max-md:grid-cols-2 gap-3">
        {metrics.map((m) => (
          <Card key={m.label} className="p-3 text-center">
            <div className={cn("text-[22px] font-semibold", m.color)}>{m.value}</div>
            <div className="text-[10px] text-secondary uppercase tracking-wider mt-0.5">{m.label}</div>
            <div className={cn("text-[10px] mt-0.5", m.trendUp ? "text-brand-green" : "text-orange-500")}>
              {m.trendUp ? "↑" : ""} {m.trend}
            </div>
          </Card>
        ))}
      </div>

      {/* Filing pipeline */}
      <Card className="p-3">
        <h3 className="text-[12px] font-semibold text-primary mb-2">Filing Pipeline</h3>
        <div className="flex max-md:flex-col gap-3">
          {pipeline.map((p) => (
            <div key={p.stage} className="flex-1 text-center">
              <Badge variant={p.badge}>{p.stage}</Badge>
              <div className="text-[18px] font-semibold text-primary mt-1">{p.count}</div>
              <div className="h-1.5 rounded-full bg-surface-tertiary mt-1 overflow-hidden">
                <div
                  className={cn("h-full rounded-full", p.color)}
                  style={{ width: `${stats.total > 0 ? (p.count / stats.total) * 100 : 0}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Deadlines + Activity */}
      <div className="grid grid-cols-2 max-md:grid-cols-1 gap-3">
        <Card className="p-3">
          <h3 className="text-[12px] font-semibold text-primary mb-2">Upcoming Deadlines</h3>
          <div className="space-y-2">
            {deadlines.map((d) => (
              <div key={d.date} className="flex items-start gap-2">
                <div className={cn("w-2 h-2 rounded-full border-2 shrink-0 mt-0.5", d.accent.replace("text-", "border-"))} />
                <div className="flex-1">
                  <div className="flex items-baseline gap-2">
                    <span className={cn("text-[11px] font-semibold", d.accent)}>{d.date}</span>
                    <span className="text-[10px] text-tertiary">{d.desc}</span>
                  </div>
                  <div className="text-[10px] text-tertiary">{stats.unfiled} client{stats.unfiled !== 1 ? "s" : ""}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-3">
          <h3 className="text-[12px] font-semibold text-primary mb-2">Recent Activity</h3>
          {stats.activity.length > 0 ? (
            <div className="space-y-2">
              {stats.activity.map((a, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className="text-[12px] shrink-0">{a.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] text-primary leading-tight">{a.text}</div>
                    <div className="text-[10px] text-tertiary">{a.time}</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[11px] text-tertiary">No recent activity</div>
          )}
        </Card>
      </div>
    </div>
  );
}
