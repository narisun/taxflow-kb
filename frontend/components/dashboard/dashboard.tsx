"use client";

import { Card } from "@/components/ui/card";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import type { Client } from "@/lib/api-client";

interface DashboardProps {
  clients: Client[];
  onSelectClient?: (id: number) => void;
}

const statusConfig: Record<string, { label: string; badge: BadgeVariant }> = {
  intake: { label: "Intake", badge: "pending" },
  documents: { label: "Documents", badge: "inProgress" },
  review: { label: "Review", badge: "review" },
  preparation: { label: "Preparation", badge: "inProgress" },
  filing: { label: "Filing", badge: "completed" },
  filed: { label: "Filed", badge: "filed" },
};

export function Dashboard({ clients, onSelectClient }: DashboardProps) {
  const totalClients = clients.length;
  const filed = clients.filter((c) => c.workflow_step === "filed").length;
  const needReview = clients.filter((c) => c.workflow_step === "review").length;
  const pending = clients.filter(
    (c) => c.workflow_step === "intake" || c.workflow_step === "documents"
  ).length;

  const metrics = [
    { label: "Total Clients", value: totalClients, color: "text-[#0071e3]" },
    { label: "Filed", value: filed, color: "text-green-600" },
    { label: "Need Review", value: needReview, color: "text-orange-600" },
    { label: "Pending", value: pending, color: "text-gray-500" },
  ];

  // Group by workflow step
  const grouped = clients.reduce(
    (acc, client) => {
      const step = client.workflow_step || "intake";
      if (!acc[step]) acc[step] = [];
      acc[step].push(client);
      return acc;
    },
    {} as Record<string, Client[]>
  );

  return (
    <div className="p-6 space-y-6 overflow-y-auto">
      {/* Metric cards */}
      <div className="grid grid-cols-4 gap-4">
        {metrics.map((m) => (
          <Card key={m.label} className="p-4 text-center">
            <div className={`text-[28px] font-semibold ${m.color}`}>
              {m.value}
            </div>
            <div className="text-[12px] text-gray-500 uppercase tracking-wider mt-1">
              {m.label}
            </div>
          </Card>
        ))}
      </div>

      {/* Pipeline */}
      <div>
        <h2 className="text-[15px] font-semibold text-[#1d1d1f] mb-3">
          Client Pipeline
        </h2>
        <div className="space-y-4">
          {Object.entries(grouped).map(([step, stepClients]) => {
            const config = statusConfig[step] || {
              label: step,
              badge: "pending" as BadgeVariant,
            };
            return (
              <div key={step}>
                <div className="flex items-center gap-2 mb-2">
                  <Badge variant={config.badge}>{config.label}</Badge>
                  <span className="text-[11px] text-gray-400">
                    ({stepClients.length})
                  </span>
                </div>
                <div className="space-y-1">
                  {stepClients.map((client) => (
                    <button
                      key={client.id}
                      onClick={() => onSelectClient?.(client.id)}
                      className="w-full text-left flex items-center justify-between px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors cursor-pointer"
                    >
                      <div>
                        <span className="text-[13px] font-medium text-[#1d1d1f]">
                          {client.name}
                        </span>
                        <span className="text-[11px] text-gray-500 ml-2">
                          {client.filing_status} / {client.tax_year}
                        </span>
                      </div>
                      <span className="text-[11px] text-gray-400">
                        {client.dependents} dep.
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
