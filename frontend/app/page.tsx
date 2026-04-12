"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { TopBar } from "@/components/layout/top-bar";
import { ClientSidebar, type Client as SidebarClient } from "@/components/layout/client-sidebar";
import { ChatPanel } from "@/components/layout/chat-panel";
import { WorkPanel } from "@/components/layout/work-panel";
import { MessageList } from "@/components/chat/message-list";
import { ChatInput } from "@/components/chat/chat-input";
import { DocumentViewerModal } from "@/components/documents/document-viewer-modal";
import { IntakeModal, type IntakeFormData } from "@/components/clients/intake-modal";
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
import { PanelOverlay } from "@/components/layout/panel-overlay";
import { BottomTabBar, type TabId } from "@/components/layout/bottom-tab-bar";
import { useIsMobile, useIsDesktopXL } from "@/lib/hooks/use-media-query";
import { useApp } from "./providers";
import { SettingsModal } from "@/components/settings/settings-modal";
import { OnboardingTour } from "@/components/onboarding/onboarding-tour";
import { AnalyticsDashboard } from "@/components/dashboard/analytics-dashboard";

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
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [showDashboard, setShowDashboard] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isMobile = useIsMobile();
  const isDesktopXL = useIsDesktopXL();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [workPanelOpen, setWorkPanelOpen] = useState(false);
  const [mobileTab, setMobileTab] = useState<TabId>("chat");

  const activeClient = sidebarClients.find((c) => c.id === activeClientId);

  // Check onboarding on mount
  useEffect(() => {
    if (!localStorage.getItem("taxflow_onboarding_complete")) {
      setShowOnboarding(true);
    }
  }, []);

  const completeOnboarding = useCallback(() => {
    localStorage.setItem("taxflow_onboarding_complete", "true");
    setShowOnboarding(false);
  }, []);

  const replayTour = useCallback(() => {
    setSettingsOpen(false);
    localStorage.removeItem("taxflow_onboarding_complete");
    setShowOnboarding(true);
  }, []);

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

  // File upload handler
  const handleFileSelected = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file || !activeClientId) return;
      e.target.value = ""; // reset so same file can be re-selected

      // Detect form type from filename
      const fname = file.name.toLowerCase();
      let formType = "Other";
      if (fname.includes("w2") || fname.includes("w-2")) formType = "W-2";
      else if (fname.includes("1099-int") || fname.includes("1099int")) formType = "1099-INT";
      else if (fname.includes("1099-nec") || fname.includes("1099nec")) formType = "1099-NEC";
      else if (fname.includes("1099-b") || fname.includes("1099b")) formType = "1099-B";
      else if (fname.includes("1099-div") || fname.includes("1099div")) formType = "1099-DIV";
      else if (fname.includes("1099")) formType = "1099";
      else if (fname.includes("1098")) formType = "1098";
      else if (fname.includes("k-1") || fname.includes("k1")) formType = "K-1";

      // Log upload start to chat
      const uploadMsg: LocalMessage = {
        id: Date.now(),
        role: "assistant",
        content: `Uploading <strong>${file.name}</strong> (${formType})...`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, uploadMsg]);

      const numId = Number(activeClientId);
      if (!isNaN(numId)) {
        try {
          const doc = await api.documents.upload(numId, file, formType);
          // Refresh documents list
          const docData = await api.documents.list(numId);
          if (Array.isArray(docData)) {
            setDocuments(docData.map((d: ApiDocument) => ({
              ...d, client_id: d.client_id, name: d.title, type: d.form_type,
            })));
          }
          // Parse extracted data for chat summary
          let summary = `<strong>${formType}</strong> uploaded and processed (${doc.confidence}% confidence).`;
          try {
            const fields = JSON.parse(doc.extracted_data);
            if (Array.isArray(fields) && fields.length > 0) {
              const details = fields.slice(0, 4).map((f: { name: string; value: string }) => `${f.name}: ${f.value}`).join(" · ");
              summary += `\n${details}`;
            }
          } catch { /* ignore parse errors */ }
          const flags = JSON.parse(doc.flags || "[]");
          if (flags.length > 0) {
            summary += `\n⚠ ${flags.length} flag(s): ${flags.join(", ")}`;
          }
          setMessages((prev) => [
            ...prev.filter((m) => m.id !== uploadMsg.id),
            { id: Date.now() + 1, role: "assistant" as const, content: summary,
              timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) },
          ]);
        } catch (err) {
          setMessages((prev) => [
            ...prev.filter((m) => m.id !== uploadMsg.id),
            { id: Date.now() + 1, role: "assistant" as const,
              content: `Failed to upload ${file.name}: ${err instanceof Error ? err.message : "Unknown error"}`,
              timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) },
          ]);
        }
      }
    },
    [activeClientId]
  );

  const handleMobileTabChange = useCallback((tab: TabId) => {
    setMobileTab(tab);
    setSidebarOpen(false);
    setWorkPanelOpen(false);
  }, []);

  const handleSelectClient = useCallback((id: string) => {
    setActiveClientId(id);
    if (isMobile) {
      setMobileTab("chat");
    }
    setSidebarOpen(false);
  }, [isMobile]);

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

  // ── Reusable content blocks ──────────────────────

  const sidebarContent = (
    <ClientSidebar
      clients={sidebarClients}
      activeClientId={activeClientId}
      onSelectClient={handleSelectClient}
      onNewIntake={() => setIntakeOpen(true)}
    />
  );

  const workPanelContent = (
    <>
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
              <div className="bg-badge-review-bg text-badge-review-text text-[12px] px-3 py-2 rounded-lg">
                &#9888; {flagMessage}
              </div>
            )}

            {documents.map((doc) => {
              const data = (() => { try { return JSON.parse(doc.extracted_data); } catch { return {}; } })();
              const fmt = (v: number | undefined) => v != null ? `$${v.toLocaleString()}` : "\u2014";
              return (
                <button
                  key={doc.id}
                  onClick={() => {
                    setViewerDoc(doc);
                    setViewerOpen(true);
                  }}
                  className="w-full text-left cursor-pointer"
                >
                  <Card className="p-3 hover:shadow-md transition-shadow">
                    {/* Header: name + small confidence pill */}
                    <div className="flex items-center justify-between mb-1.5">
                      <div>
                        <div className="text-[13px] font-medium text-primary">
                          {doc.name}
                        </div>
                        <div className="text-[11px] text-tertiary">
                          {doc.form_type} &middot; TY 2025
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Badge
                          variant={
                            doc.status === "verified" ? "completed"
                              : doc.status === "flagged" ? "review"
                              : "pending"
                          }
                        >
                          {doc.confidence}%
                        </Badge>
                      </div>
                    </div>

                    {/* Extracted amounts — key financial data */}
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
                      {data.wages != null && (
                        <>
                          <span className="text-tertiary">Wages</span>
                          <span className="text-right text-primary font-medium">{fmt(data.wages)}</span>
                        </>
                      )}
                      {data.federal_tax_withheld != null && (
                        <>
                          <span className="text-tertiary">Fed W/H</span>
                          <span className="text-right text-primary font-medium">{fmt(data.federal_tax_withheld)}</span>
                        </>
                      )}
                      {data.state && data.state_tax != null && (
                        <>
                          <span className="text-tertiary">{data.state} W/H</span>
                          <span className="text-right text-primary font-medium">{fmt(data.state_tax)}</span>
                        </>
                      )}
                      {data.interest_income != null && (
                        <>
                          <span className="text-tertiary">Interest</span>
                          <span className="text-right text-primary font-medium">{fmt(data.interest_income)}</span>
                        </>
                      )}
                      {data.mortgage_interest != null && (
                        <>
                          <span className="text-tertiary">Mort. Int.</span>
                          <span className="text-right text-primary font-medium">{fmt(data.mortgage_interest)}</span>
                        </>
                      )}
                      {data.real_estate_taxes != null && (
                        <>
                          <span className="text-tertiary">RE Taxes</span>
                          <span className="text-right text-primary font-medium">{fmt(data.real_estate_taxes)}</span>
                        </>
                      )}
                    </div>
                  </Card>
                </button>
              );
            })}
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
            <div className="w-12 h-12 rounded-full bg-green-100 dark:bg-green-950/30 text-green-600 dark:text-green-400 flex items-center justify-center text-[24px] mb-3">
              &#10003;
            </div>
            <div className="text-[15px] font-semibold text-primary mb-1">
              Return Filed
            </div>
            <div className="text-[12px] text-secondary">
              Submitted 04/10/2026
            </div>
            <Badge variant="filed" className="mt-3">
              E-Filed
            </Badge>
          </div>
        )}
      </div>
    </>
  );

  const chatContent = (
    <main className="flex-1 flex flex-col bg-surface min-w-0">
      {/* Context bar */}
      <div className="shrink-0 border-b border-divider px-5 py-3">
        {/* Top row: client info + tracking labels */}
        <div className="flex items-center gap-3">
          <div className="flex-1 min-w-0 flex items-center gap-3">
            <span className="text-[14px] font-semibold text-primary">
              {activeClient?.name || "Select a client"}
            </span>
            {activeClient && (
              <>
                <span className="text-[11px] text-tertiary hidden md:inline">{activeClient.meta}</span>
                <Badge variant={activeClient.status as "pending" | "inProgress" | "review" | "completed" | "filed"}>
                  {activeClient.status === "inProgress" ? "In Progress" : activeClient.status}
                </Badge>
              </>
            )}
          </div>

          {/* Work panel toggle — visible below XL */}
          {!isDesktopXL && !isMobile && (
            <button
              onClick={() => setWorkPanelOpen(!workPanelOpen)}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-secondary hover:bg-surface-secondary transition-colors cursor-pointer"
              aria-label="Toggle work panel"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                <path d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          )}

          {/* Federal / State tracking labels */}
          <span className="hidden xl:inline text-[12px] font-semibold text-green-600 dark:text-green-400 bg-surface-secondary px-2.5 py-1 rounded-md">
            Federal: +$4,820
          </span>
          <span className="hidden xl:inline text-[12px] font-semibold text-red-500 dark:text-red-400 bg-surface-secondary px-2.5 py-1 rounded-md">
            NJ: -$1,240
          </span>
        </div>

        {/* Second row: tax season + workflow stepper */}
        <div className="hidden md:flex items-center gap-3 mt-2">
          <Badge variant="inProgress">2025 Tax Season</Badge>
          <div className="w-px h-4 bg-divider" />
          <div className="flex items-center gap-1">
            {["Intake", "Documents", "Review", "Prepare", "File"].map(
              (step, i) => (
                <div key={step} className="flex items-center gap-1">
                  {i > 0 && <div className="w-4 h-px bg-divider" />}
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
      </div>

      {/* Messages */}
      <MessageList messages={messages} isTyping={isTyping} />

      {/* Hidden file input for document upload */}
      <input
        type="file"
        ref={fileInputRef}
        className="hidden"
        accept=".pdf,.png,.jpg,.jpeg,.tiff"
        onChange={handleFileSelected}
      />

      {/* Input */}
      <ChatInput
        onSend={handleSendMessage}
        onAttach={() => fileInputRef.current?.click()}
      />
    </main>
  );

  // ── Render ─────────────────────────────────────

  return (
    <div className="flex flex-col h-full">
      <TopBar
        stats={{ clients: totalClients, filed: filedCount, review: reviewCount }}
        deadline="April 15 in 4 days"
        user={{ initials: "SC" }}
        showMenu={!isDesktopXL}
        onMenuToggle={() => setSidebarOpen(!sidebarOpen)}
        clientName={isMobile ? activeClient?.name : undefined}
        onDashboard={() => setShowDashboard(!showDashboard)}
        onAvatarClick={() => setSettingsOpen(true)}
      />

      {isMobile ? (
        /* ── Mobile layout: single panel + bottom tabs ── */
        <>
          <div className="flex-1 overflow-hidden flex flex-col">
            {mobileTab === "clients" && (
              <div className="flex-1 overflow-y-auto">{sidebarContent}</div>
            )}
            {mobileTab === "chat" && (showDashboard ? <AnalyticsDashboard /> : chatContent)}
            {mobileTab === "docs" && (
              <div className="flex-1 overflow-y-auto flex flex-col">{workPanelContent}</div>
            )}
            {mobileTab === "returns" && (
              <div className="flex-1 overflow-y-auto flex flex-col">
                <Tabs
                  tabs={["Tax Return", "Filed"]}
                  activeTab={activeWorkTab === "Documents" ? "Tax Return" : activeWorkTab}
                  onTabChange={setActiveWorkTab}
                  className="px-2 pt-1"
                />
                <div className="flex-1 overflow-y-auto p-3">
                  {(activeWorkTab === "Tax Return" || activeWorkTab === "Documents") && (
                    <ReturnPreview
                      lines={returnDraft ? returnDraft.lines : undefined}
                      refundOrOwed={returnDraft?.refund_or_owed}
                      effectiveRate={returnDraft?.effective_rate}
                      onViewFull={handleGenerateReturn}
                    />
                  )}
                  {activeWorkTab === "Filed" && (
                    <div className="flex flex-col items-center justify-center h-64 text-center">
                      <div className="w-12 h-12 rounded-full bg-green-100 dark:bg-green-950/30 text-green-600 dark:text-green-400 flex items-center justify-center text-[24px] mb-3">
                        &#10003;
                      </div>
                      <div className="text-[15px] font-semibold text-primary mb-1">Return Filed</div>
                      <div className="text-[12px] text-secondary">Submitted 04/10/2026</div>
                      <Badge variant="filed" className="mt-3">E-Filed</Badge>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
          <BottomTabBar
            activeTab={mobileTab}
            onTabChange={handleMobileTabChange}
            docBadge={documents.filter((d) => d.status === "flagged" || d.status === "pending").length}
          />
        </>
      ) : (
        /* ── Tablet / Desktop / XL layout ── */
        <div className="flex flex-1 overflow-hidden">
          {/* Sidebar — inline on lg+, overlay on tablet */}
          <div className="hidden lg:block">{sidebarContent}</div>

          {/* Chat panel */}
          {showDashboard ? <AnalyticsDashboard /> : chatContent}

          {/* Work panel — inline on XL, overlay below */}
          {isDesktopXL && (
            <aside className="w-96 shrink-0 bg-surface border-l border-divider flex flex-col overflow-hidden">
              {workPanelContent}
            </aside>
          )}
        </div>
      )}

      {/* Sidebar overlay — tablet (below lg) */}
      {!isMobile && (
        <PanelOverlay open={sidebarOpen} onClose={() => setSidebarOpen(false)} side="left" className="w-72">
          {sidebarContent}
        </PanelOverlay>
      )}

      {/* Work panel overlay — tablet/laptop (below XL) */}
      {!isMobile && !isDesktopXL && (
        <PanelOverlay open={workPanelOpen} onClose={() => setWorkPanelOpen(false)} side="right" className="w-96">
          <div className="flex flex-col h-full">{workPanelContent}</div>
        </PanelOverlay>
      )}

      {/* Document viewer modal */}
      <DocumentViewerModal
        open={viewerOpen}
        onClose={() => setViewerOpen(false)}
        document={viewerDoc}
        onApprove={handleApproveDoc}
      />

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onReplayTour={replayTour}
      />

      <OnboardingTour
        active={showOnboarding}
        onComplete={completeOnboarding}
      />

      <IntakeModal
        open={intakeOpen}
        onClose={() => setIntakeOpen(false)}
        onSubmit={async (data: IntakeFormData) => {
          const name = data.spouseFirstName
            ? `${data.lastName} Family`
            : `${data.lastName}, ${data.firstName}`;
          const filingLabel = FILING_STATUS_LABELS[data.filingStatus] || data.filingStatus;

          try {
            // Create client via backend API
            const created = await api.clients.create({
              name,
              filing_status: data.filingStatus,
              tax_year: data.taxYear,
              dependents: data.dependents,
            });
            const newId = String(created.id);
            const meta = [
              data.spouseFirstName ? `${data.firstName} & ${data.spouseFirstName}` : data.firstName,
              filingLabel,
              data.dependents > 0 ? `${data.dependents} dep.` : null,
            ].filter(Boolean).join(" \u00b7 ");

            setSidebarClients((prev) => [
              {
                id: newId, name, meta, status: "pending",
                initials: name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase(),
                color: hashColor(name),
              },
              ...prev,
            ]);
            setActiveClientId(newId);
            setUsingApi(true);

            // Log to chat via API
            const filingDesc = [data.filingFederal ? "Federal" : "", ...data.filingStates].filter(Boolean).join(", ");
            await api.chat.send(created.id, `[System] New client intake: ${name}, ${filingLabel}, TY ${data.taxYear}. Filing: ${filingDesc}.`);

            // Reload chat
            const chatData = await api.chat.history(created.id);
            if (Array.isArray(chatData)) {
              setMessages(chatData.map((m: ChatMessage) => ({
                id: m.id, role: m.role, content: m.content,
                timestamp: new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
              })));
            }
            setDocuments([]);
          } catch {
            // Fallback: local-only
            const newId = String(Date.now());
            setSidebarClients((prev) => [
              { id: newId, name, meta: filingLabel, status: "pending", initials: name.slice(0, 2).toUpperCase(), color: "#6B7280" },
              ...prev,
            ]);
            setActiveClientId(newId);
            setMessages([{
              id: "intake-" + newId, role: "assistant" as const,
              content: `New intake created for ${name} (${data.taxYear}). Ready to upload documents.`,
              timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
            }]);
          }
        }}
      />
    </div>
  );
}

const FILING_STATUS_LABELS: Record<string, string> = {
  single: "Single",
  mfj: "MFJ",
  mfs: "MFS",
  hoh: "HOH",
  qw: "QSS",
};

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
