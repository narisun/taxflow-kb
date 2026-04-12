// frontend/components/dashboard/analytics-dashboard.tsx
"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// TODO: wire to real API — all values below are placeholder mock data

const metrics = [
  { label: "Total Clients", value: "67", trend: "+3", trendUp: true, color: "text-apple-blue" },
  { label: "Returns Filed", value: "42", trend: "63%", trendUp: true, color: "text-green-600 dark:text-green-400" },
  { label: "Pending Review", value: "12", trend: "5 urgent", trendUp: false, color: "text-orange-500" },
  { label: "Revenue", value: "$148,500", trend: "+12% YoY", trendUp: true, color: "text-green-600 dark:text-green-400" },
];

const pipeline = [
  { stage: "Intake", count: 8, color: "bg-badge-pending-bg", badge: "pending" as const },
  { stage: "Documents", count: 12, color: "bg-badge-progress-bg", badge: "inProgress" as const },
  { stage: "Review", count: 15, color: "bg-badge-review-bg", badge: "review" as const },
  { stage: "Filing", count: 18, color: "bg-badge-complete-bg", badge: "completed" as const },
  { stage: "Complete", count: 14, color: "bg-badge-filed-bg", badge: "filed" as const },
];

const deadlines = [
  { date: "Apr 15, 2026", desc: "Individual returns", clients: 8, accent: "text-red-500" },
  { date: "Jun 15, 2026", desc: "Estimated Q2 payments", clients: 3, accent: "text-orange-500" },
  { date: "Sep 15, 2026", desc: "Extension deadline", clients: 2, accent: "text-yellow-600 dark:text-yellow-400" },
  { date: "Jan 15, 2027", desc: "Estimated Q4 payments", clients: 1, accent: "text-tertiary" },
];

const activity = [
  { icon: "⬆", text: "Sarah Johnson's W-2 uploaded", time: "2h ago" },
  { icon: "🔍", text: "Data extracted from Mike Chen's 1099-INT", time: "5h ago" },
  { icon: "📄", text: "Draft return generated for Lisa Park", time: "8h ago" },
  { icon: "💬", text: "New response for David Kim's query", time: "1d ago" },
  { icon: "👤", text: "New client James Wright added", time: "1d ago" },
];

const seasonTotal = 67;
const seasonFiled = 42;
const seasonReview = 12;
const seasonPending = seasonTotal - seasonFiled - seasonReview;

export function AnalyticsDashboard() {
  return (
    <div className="p-6 max-md:p-4 space-y-6 overflow-y-auto h-full">
      <h2 className="text-[17px] font-semibold text-primary">Dashboard</h2>

      {/* Row 1: Metric cards */}
      <div className="grid grid-cols-4 max-md:grid-cols-2 gap-4 max-md:gap-3">
        {metrics.map((m) => (
          <Card key={m.label} className="p-5 max-md:p-4 text-center">
            <div className={cn("text-[28px] max-md:text-[24px] font-semibold", m.color)}>{m.value}</div>
            <div className="text-[11px] text-secondary uppercase tracking-wider mt-1">{m.label}</div>
            <div className={cn("text-[11px] mt-1", m.trendUp ? "text-green-600 dark:text-green-400" : "text-orange-500")}>
              {m.trendUp ? "↑" : ""} {m.trend}
            </div>
          </Card>
        ))}
      </div>

      {/* Row 2: Filing pipeline */}
      <Card className="p-5">
        <h3 className="text-[13px] font-semibold text-primary mb-4">Filing Pipeline</h3>
        <div className="flex max-md:flex-col gap-3">
          {pipeline.map((p) => (
            <div key={p.stage} className="flex-1 text-center">
              <Badge variant={p.badge}>{p.stage}</Badge>
              <div className="text-[20px] font-semibold text-primary mt-2">{p.count}</div>
              <div className="h-2 rounded-full bg-surface-tertiary mt-2 overflow-hidden">
                <div
                  className={cn("h-full rounded-full", p.color)}
                  style={{ width: `${(p.count / seasonTotal) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Row 3: Deadlines + Activity */}
      <div className="grid grid-cols-2 max-md:grid-cols-1 gap-4">
        {/* Deadline timeline */}
        <Card className="p-5">
          <h3 className="text-[13px] font-semibold text-primary mb-4">Upcoming Deadlines</h3>
          <div className="space-y-4">
            {deadlines.map((d) => (
              <div key={d.date} className="flex items-start gap-3">
                <div className="flex flex-col items-center">
                  <div className={cn("w-2.5 h-2.5 rounded-full border-2 shrink-0", d.accent.replace("text-", "border-"))} />
                  <div className="w-px h-8 bg-divider last:hidden" />
                </div>
                <div className="flex-1">
                  <div className={cn("text-[12px] font-semibold", d.accent)}>{d.date}</div>
                  <div className="text-[12px] text-primary">{d.desc}</div>
                  <div className="text-[11px] text-tertiary">{d.clients} client{d.clients > 1 ? "s" : ""}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Activity feed */}
        <Card className="p-5">
          <h3 className="text-[13px] font-semibold text-primary mb-4">Recent Activity</h3>
          <div className="space-y-3">
            {activity.map((a, i) => (
              <div key={i} className="flex items-start gap-3">
                <span className="text-[14px] mt-0.5 shrink-0">{a.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-[12px] text-primary">{a.text}</div>
                  <div className="text-[11px] text-tertiary">{a.time}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Row 4: Season progress */}
      <Card className="p-5">
        <h3 className="text-[13px] font-semibold text-primary mb-3">
          Tax Season 2025: {seasonFiled} of {seasonTotal} returns filed ({Math.round((seasonFiled / seasonTotal) * 100)}%)
        </h3>
        <div className="h-3 rounded-full bg-surface-tertiary overflow-hidden flex">
          <div className="bg-green-500 h-full" style={{ width: `${(seasonFiled / seasonTotal) * 100}%` }} />
          <div className="bg-orange-500 h-full" style={{ width: `${(seasonReview / seasonTotal) * 100}%` }} />
        </div>
        <div className="flex gap-4 mt-2 text-[11px]">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500" /> Filed ({seasonFiled})</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-orange-500" /> Review ({seasonReview})</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-surface-tertiary" /> Pending ({seasonPending})</span>
        </div>
      </Card>
    </div>
  );
}
