"use client";

import { useState, useEffect, useCallback } from "react";
import { TopBar } from "@/components/layout/top-bar";
import { ClientSidebar, type Client as SidebarClient } from "@/components/layout/client-sidebar";
import { ChatPanel } from "@/components/layout/chat-panel";
import { WorkPanel } from "@/components/layout/work-panel";
import { MessageList } from "@/components/chat/message-list";
import { ChatInput } from "@/components/chat/chat-input";
import { DocumentViewerModal } from "@/components/documents/document-viewer-modal";
import { ReturnPreview } from "@/components/returns/return-preview";
import { Dashboard } from "@/components/dashboard/dashboard";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Tabs } from "@/components/ui/tabs";
import { api } from "@/lib/api-client";
import type {
  Client as ApiClient,
  ChatMessage,
  Document as ApiDocument,
  TaxReturnDraft,
} from "@/lib/api-client";
import { useApp } from "./providers";

// ────────────────────────────────────────────
// Mock data for offline / fallback mode
// ────────────────────────────────────────────

const mockSidebarClients: SidebarClient[] = [
  {
    id: "1",
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
    id: "2",
    name: "Johnson Family",
    meta: "Robert & Maria \u00b7 MFJ \u00b7 3 dep.",
    status: "review",
    initials: "JO",
    color: "#9A3412",
    years: [{ year: "2025", docs: ["W-2", "1099-NEC", "Schedule C"] }],
  },
  {
    id: "3",
    name: "Wei Chen",
    meta: "Single \u00b7 0 dep. \u00b7 Self-employed",
    status: "pending",
    initials: "WC",
    color: "#7C3AED",
  },
  {
    id: "4",
    name: "Garcia Household",
    meta: "Carlos & Ana \u00b7 MFJ \u00b7 4 dep.",
    status: "completed",
    initials: "GA",
    color: "#047857",
  },
  {
    id: "5",
    name: "Patel Family",
    meta: "Raj & Priya \u00b7 MFJ \u00b7 1 dep.",
    status: "filed",
    initials: "PA",
    color: "#B45309",
  },
];

interface LocalMessage {
  id: string | number;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  created_at?: string;
}

const mockMessages: LocalMessage[] = [
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
];

interface LocalDoc {
  id: number;
  form_type: string;
  title: string;
  status: string;
  confidence: number;
  extracted_data: string;
  flags: string;
  name: string;
  type: string;
}

const mockDocuments: LocalDoc[] = [
  {
    id: 1,
    name: "W-2 (John)",
    type: "Income",
    form_type: "W-2",
    title: "W-2 (John Smith)",
    status: "verified",
    confidence: 97,
    extracted_data: JSON.stringify({
      employer_name: "Acme Corp",
      employer_ein: "12-3456789",
      employee_name: "John Smith",
      wages: 85000,
      federal_tax_withheld: 12750,
      social_security_wages: 85000,
      social_security_tax: 5270,
      medicare_wages: 85000,
      medicare_tax: 1232.5,
      state: "CA",
      state_wages: 85000,
      state_tax: 4250,
    }),
    flags: "[]",
  },
  {
    id: 2,
    name: "W-2 (Jane)",
    type: "Income",
    form_type: "W-2",
    title: "W-2 (Jane Smith)",
    status: "verified",
    confidence: 94,
    extracted_data: JSON.stringify({
      employer_name: "TechStart Inc",
      employer_ein: "98-7654321",
      employee_name: "Jane Smith",
      wages: 57500,
      federal_tax_withheld: 7950,
      social_security_wages: 57500,
      social_security_tax: 3565,
      medicare_wages: 57500,
      medicare_tax: 833.75,
      state: "CA",
      state_wages: 57500,
      state_tax: 2875,
    }),
    flags: "[]",
  },
  {
    id: 3,
    name: "1099-INT",
    type: "Interest",
    form_type: "1099-INT",
    title: "1099-INT (First National Bank)",
    status: "flagged",
    confidence: 88,
    extracted_data: JSON.stringify({
      payer_name: "First National Bank",
      payer_tin: "**-***4521",
      recipient_name: "John Smith",
      interest_income: 1230,
      federal_tax_withheld: 0,
    }),
    flags: JSON.stringify(["Payer TIN mismatch - expected ending 4512, found 4521"]),
  },
  {
    id: 4,
    name: "1098 Mortgage",
    type: "Deduction",
    form_type: "1098",
    title: "1098 Mortgage Interest Statement",
    status: "verified",
    confidence: 92,
    extracted_data: JSON.stringify({
      lender_name: "Wells Fargo Home Mortgage",
      mortgage_interest: 12500,
      real_estate_taxes: 4800,
      mortgage_insurance: 0,
      outstanding_principal: 320000,
    }),
    flags: "[]",
  },
];

// ────────────────────────────────────────────
// Page component
// ────────────────────────────────────────────

export default function Home() {
  const {
    activeClientId: apiClientId,
    setActiveClientId: setApiClientId,
    clients: apiClients,
    setClients: setApiClients,
    messages: apiMessages,
    setMessages: setApiMessages,
    documents: apiDocuments,
    setDocuments: setApiDocuments,
  } = useApp();

  const [activeClientId, setActiveClientId] = useState<string | null>("1");
  const [messages, setMessages] = useState<LocalMessage[]>(mockMessages);
  const [documents, setDocuments] = useState<LocalDoc[]>(mockDocuments);
  const [sidebarClients, setSidebarClients] =
    useState<SidebarClient[]>(mockSidebarClients);
  const [isTyping, setIsTyping] = useState(false);
  const [viewerDoc, setViewerDoc] = useState<LocalDoc | null>(null);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [activeWorkTab, setActiveWorkTab] = useState("Documents");
  const [usingApi, setUsingApi] = useState(false);
  const [returnDraft, setReturnDraft] = useState<TaxReturnDraft | null>(null);

  const activeClient = sidebarClients.find((c) => c.id === activeClientId);

  // Try loading from API on mount
  useEffect(() => {
    let cancelled = false;
    async function loadClients() {
      try {
        const data = await api.clients.list();
        if (cancelled || !Array.isArray(data) || data.length === 0) return;
        setApiClients(data);
        setUsingApi(true);
        // Convert API clients to sidebar format
        const converted: SidebarClient[] = data.map((c: ApiClient) => ({
          id: String(c.id),
          name: c.name,
          meta: `${c.filing_status} \u00b7 ${c.dependents} dep. \u00b7 ${c.tax_year}`,
          status: mapWorkflowStep(c.workflow_step),
          initials: c.name
            .split(" ")
            .map((w) => w[0])
            .join("")
            .slice(0, 2)
            .toUpperCase(),
          color: hashColor(c.name),
        }));
        setSidebarClients(converted);
        if (converted.length > 0) setActiveClientId(converted[0].id);
      } catch {
        // API unavailable — use mock data
      }
    }
    loadClients();
    return () => {
      cancelled = true;
    };
  }, [setApiClients]);

  // Load chat and documents when active client changes
  useEffect(() => {
    if (!activeClientId) return;
    const numId = Number(activeClientId);
    if (!usingApi || isNaN(numId)) {
      // Use mock data
      setMessages(mockMessages);
      setDocuments(mockDocuments);
      return;
    }

    let cancelled = false;
    async function loadClientData() {
      try {
        const [chatData, docData] = await Promise.all([
          api.chat.history(numId),
          api.documents.list(numId),
        ]);
        if (cancelled) return;
        if (Array.isArray(chatData)) {
          setApiMessages(chatData);
          setMessages(
            chatData.map((m: ChatMessage) => ({
              id: m.id,
              role: m.role,
              content: m.content,
              timestamp: new Date(m.created_at).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              }),
              created_at: m.created_at,
            }))
          );
        }
        if (Array.isArray(docData)) {
          setApiDocuments(docData);
          setDocuments(
            docData.map((d: ApiDocument) => ({
              ...d,
              client_id: d.client_id,
              name: d.title,
              type: d.form_type,
            }))
          );
        }
      } catch {
        // Fallback to mock
        setMessages(mockMessages);
        setDocuments(mockDocuments);
      }
    }
    loadClientData();
    return () => {
      cancelled = true;
    };
  }, [activeClientId, usingApi, setApiMessages, setApiDocuments]);

  // Send message handler
  const handleSendMessage = useCallback(
    async (content: string) => {
      const newUserMsg: LocalMessage = {
        id: Date.now(),
        role: "user",
        content,
        timestamp: new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
      };
      setMessages((prev) => [...prev, newUserMsg]);
      setIsTyping(true);

      const numId = Number(activeClientId);
      if (usingApi && !isNaN(numId)) {
        try {
          const response = await api.chat.send(numId, content);
          setIsTyping(false);
          if (response && response.content) {
            setMessages((prev) => [
              ...prev,
              {
                id: response.id || Date.now() + 1,
                role: "assistant",
                content: response.content,
                timestamp: new Date(
                  response.created_at || Date.now()
                ).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                }),
              },
            ]);
          }
          return;
        } catch {
          // Fall through to mock response
        }
      }

      // Mock AI response
      setTimeout(() => {
        setIsTyping(false);
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now() + 1,
            role: "assistant" as const,
            content: `I'll look into that for you. Based on the documents I have for ${activeClient?.name || "this client"}, here's what I found regarding "${content}".`,
            timestamp: new Date().toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            }),
          },
        ]);
      }, 1500);
    },
    [activeClientId, usingApi, activeClient?.name]
  );

  // Document approve handler
  const handleApproveDoc = useCallback(
    async (docId: number) => {
      if (usingApi) {
        try {
          await api.documents.approve(docId);
        } catch {
          // Silently fall through
        }
      }
      setDocuments((prev) =>
        prev.map((d) =>
          d.id === docId ? { ...d, status: "verified" } : d
        )
      );
    },
    [usingApi]
  );

  // Generate return draft
  const handleGenerateReturn = useCallback(async () => {
    const numId = Number(activeClientId);
    if (usingApi && !isNaN(numId)) {
      try {
        const draft = await api.returns.draft(numId);
        setReturnDraft(draft);
        return;
      } catch {
        // Fall through
      }
    }
  }, [activeClientId, usingApi]);

  // Stats
  const totalClients = sidebarClients.length;
  const filedCount = sidebarClients.filter((c) => c.status === "filed").length;
  const reviewCount = sidebarClients.filter(
    (c) => c.status === "review"
  ).length;

  const flagMessage =
    documents.filter((d) => d.status === "flagged" || d.status === "pending")
      .length > 0
      ? `${documents.filter((d) => d.status === "flagged" || d.status === "pending").length} documents need review before filing`
      : "";

  return (
    <div className="flex flex-col h-full">
      <TopBar
        stats={{ clients: totalClients, filed: filedCount, review: reviewCount }}
        deadline="April 15 in 4 days"
        user={{ initials: "SC" }}
      />
      <div className="flex flex-1 overflow-hidden">
        <ClientSidebar
          clients={sidebarClients}
          activeClientId={activeClientId}
          onSelectClient={setActiveClientId}
        />

        {/* Chat panel - custom wired version */}
        <main className="flex-1 flex flex-col bg-white min-w-0">
          {/* Context bar */}
          <div className="h-12 shrink-0 border-b border-gray-100 flex items-center px-4 gap-3">
            <Avatar
              initials={activeClient?.initials || "??"}
              color={activeClient?.color || "#6B7280"}
              size="sm"
            />
            <span className="text-[13px] font-semibold text-[#1d1d1f]">
              {activeClient?.name || "Select a client"}
            </span>

            {/* Workflow stepper */}
            <div className="flex items-center gap-1 ml-4">
              {["Intake", "Documents", "Review", "Prepare", "File"].map(
                (step, i) => (
                  <div key={step} className="flex items-center gap-1">
                    {i > 0 && <div className="w-4 h-px bg-gray-300" />}
                    <Badge
                      variant={
                        i < 2
                          ? "completed"
                          : i === 2
                            ? "inProgress"
                            : "pending"
                      }
                    >
                      {step}
                    </Badge>
                  </div>
                )
              )}
            </div>
          </div>

          {/* Messages */}
          <MessageList messages={messages} isTyping={isTyping} />

          {/* Input */}
          <ChatInput onSend={handleSendMessage} />
        </main>

        {/* Work panel */}
        <aside className="w-96 shrink-0 bg-white border-l border-gray-200 flex flex-col overflow-hidden">
          <Tabs
            tabs={["Documents", "Tax Return", "Filed"]}
            activeTab={activeWorkTab}
            onTabChange={setActiveWorkTab}
            className="px-2 pt-1"
          />

          <div className="flex-1 overflow-y-auto p-3">
            {activeWorkTab === "Documents" && (
              <div className="space-y-3">
                {flagMessage && (
                  <div className="bg-orange-50 text-orange-700 text-[12px] px-3 py-2 rounded-lg">
                    &#9888; {flagMessage}
                  </div>
                )}

                {documents.map((doc) => (
                  <button
                    key={doc.id}
                    onClick={() => {
                      setViewerDoc(doc);
                      setViewerOpen(true);
                    }}
                    className="w-full text-left cursor-pointer"
                  >
                    <Card className="p-3 hover:shadow-md transition-shadow">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[13px] font-medium text-[#1d1d1f]">
                          {doc.name}
                        </span>
                        <Badge
                          variant={
                            doc.status === "verified"
                              ? "completed"
                              : doc.status === "flagged"
                                ? "review"
                                : "pending"
                          }
                        >
                          {doc.status}
                        </Badge>
                      </div>
                      <div className="text-[11px] text-gray-500 mb-1.5">
                        {doc.type}
                      </div>
                      <div className="flex items-center gap-2">
                        <Progress
                          value={doc.confidence}
                          color={
                            doc.confidence >= 90
                              ? "green"
                              : doc.confidence >= 70
                                ? "orange"
                                : "red"
                          }
                          className="flex-1"
                        />
                        <span className="text-[10px] text-gray-400 w-8 text-right">
                          {doc.confidence}%
                        </span>
                      </div>
                    </Card>
                  </button>
                ))}
              </div>
            )}

            {activeWorkTab === "Tax Return" && (
              <ReturnPreview
                lines={
                  returnDraft
                    ? returnDraft.lines
                    : undefined
                }
                refundOrOwed={returnDraft?.refund_or_owed}
                effectiveRate={returnDraft?.effective_rate}
                onViewFull={handleGenerateReturn}
              />
            )}

            {activeWorkTab === "Filed" && (
              <div className="flex flex-col items-center justify-center h-64 text-center">
                <div className="w-12 h-12 rounded-full bg-green-100 text-green-600 flex items-center justify-center text-[24px] mb-3">
                  &#10003;
                </div>
                <div className="text-[15px] font-semibold text-[#1d1d1f] mb-1">
                  Return Filed
                </div>
                <div className="text-[12px] text-gray-500">
                  Submitted 04/10/2026
                </div>
                <Badge variant="filed" className="mt-3">
                  E-Filed
                </Badge>
              </div>
            )}
          </div>
        </aside>
      </div>

      {/* Document viewer modal */}
      <DocumentViewerModal
        open={viewerOpen}
        onClose={() => setViewerOpen(false)}
        document={viewerDoc}
        onApprove={handleApproveDoc}
      />
    </div>
  );
}

// ────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────

function mapWorkflowStep(step: string): string {
  switch (step) {
    case "intake":
      return "pending";
    case "documents":
    case "preparation":
      return "inProgress";
    case "review":
      return "review";
    case "filing":
      return "completed";
    case "filed":
      return "filed";
    default:
      return "pending";
  }
}

function hashColor(name: string): string {
  const colors = [
    "#1D4ED8",
    "#9A3412",
    "#7C3AED",
    "#047857",
    "#B45309",
    "#DC2626",
    "#0891B2",
    "#4338CA",
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
}
