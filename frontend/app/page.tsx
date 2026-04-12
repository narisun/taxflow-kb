"use client";

import { useState } from "react";
import { TopBar } from "@/components/layout/top-bar";
import { ClientSidebar, type Client } from "@/components/layout/client-sidebar";
import { ChatPanel } from "@/components/layout/chat-panel";
import { WorkPanel } from "@/components/layout/work-panel";

const mockClients: Client[] = [
  {
    id: "smith",
    name: "Smith Family",
    meta: "John & Jane \u00b7 MFJ \u00b7 2 dep.",
    status: "inProgress",
    initials: "SM",
    color: "#1D4ED8",
    years: [
      { year: "2025", docs: ["W-2 (John)", "W-2 (Jane)", "1099-INT", "1098"] },
      { year: "2024", docs: ["W-2 (John)", "W-2 (Jane)"] },
    ],
  },
  {
    id: "johnson",
    name: "Johnson Family",
    meta: "Robert & Maria \u00b7 MFJ \u00b7 3 dep.",
    status: "review",
    initials: "JO",
    color: "#9A3412",
    years: [{ year: "2025", docs: ["W-2", "1099-NEC", "Schedule C"] }],
  },
  {
    id: "chen",
    name: "Wei Chen",
    meta: "Single \u00b7 0 dep. \u00b7 Self-employed",
    status: "pending",
    initials: "WC",
    color: "#7C3AED",
  },
  {
    id: "garcia",
    name: "Garcia Household",
    meta: "Carlos & Ana \u00b7 MFJ \u00b7 4 dep.",
    status: "completed",
    initials: "GA",
    color: "#047857",
  },
  {
    id: "patel",
    name: "Patel Family",
    meta: "Raj & Priya \u00b7 MFJ \u00b7 1 dep.",
    status: "filed",
    initials: "PA",
    color: "#B45309",
  },
];

export default function Home() {
  const [activeClientId, setActiveClientId] = useState<string | null>("smith");

  const activeClient = mockClients.find((c) => c.id === activeClientId);

  return (
    <div className="flex flex-col h-full">
      <TopBar
        stats={{ clients: 47, filed: 12, review: 8 }}
        deadline="April 15 in 4 days"
        user={{ initials: "SC" }}
      />
      <div className="flex flex-1 overflow-hidden">
        <ClientSidebar
          clients={mockClients}
          activeClientId={activeClientId}
          onSelectClient={setActiveClientId}
        />
        <ChatPanel
          clientName={activeClient?.name}
          clientInitials={activeClient?.initials}
          clientColor={activeClient?.color}
          messages={[
            {
              id: "1",
              role: "assistant",
              content:
                "I\u2019ve loaded the Smith Family return. I see 4 documents uploaded for 2025. The W-2s look good, but the 1099-INT needs review \u2014 the payer TIN doesn\u2019t match IRS records.",
              timestamp: "10:32 AM",
            },
            {
              id: "2",
              role: "user",
              content: "Can you show me the 1099-INT discrepancy?",
              timestamp: "10:33 AM",
            },
            {
              id: "3",
              role: "assistant",
              content:
                "The 1099-INT from First National Bank shows TIN ending in 4521, but our IRS match database expects 4512. This is likely a transposition error. I recommend contacting the bank for a corrected form.",
              timestamp: "10:33 AM",
            },
          ]}
        />
        <WorkPanel />
      </div>
    </div>
  );
}
