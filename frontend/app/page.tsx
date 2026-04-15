"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { cn } from "@/lib/utils";
import { TopBar } from "@/components/layout/top-bar";
import { ClientSidebar, type Client as SidebarClient } from "@/components/layout/client-sidebar";
import { MessageList } from "@/components/chat/message-list";
import { ChatInput } from "@/components/chat/chat-input";
import { DocumentViewerModal } from "@/components/documents/document-viewer-modal";
import { IntakeModal, type IntakeFormData } from "@/components/clients/intake-modal";
import { ReturnPreview } from "@/components/returns/return-preview";
import { FilingWorkflow } from "@/components/returns/filing-workflow";
import { AdvisoryPanel } from "@/components/returns/advisory-panel";
import { InboxModal } from "@/components/inbox/inbox-modal";
import { ClientMasterModal } from "@/components/clients/client-master-modal";
import { DashboardModal } from "@/components/dashboard/dashboard-modal";
import { ResearchAgentModal } from "@/components/research/research-agent-modal";
import { DocumentCard } from "@/components/documents/document-card";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Tabs } from "@/components/ui/tabs";
import { api } from "@/lib/api-client";
import { mockApi } from "@/lib/mock-api";
import { mockAdults } from "@/lib/mock-data";
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

// ────────────────────────────────────────────
// Page component
// ────────────────────────────────────────────

interface LocalMessage {
  id: string | number;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  created_at?: string;
}

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
  created_at?: string;
}

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

  const [activeClientId, setActiveClientId] = useState<string | null>(null);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [documents, setDocuments] = useState<LocalDoc[]>([]);
  const [sidebarClients, setSidebarClients] =
    useState<SidebarClient[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [viewerDoc, setViewerDoc] = useState<LocalDoc | null>(null);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [activeWorkTab, setActiveWorkTab] = useState("Documents");
  const [usingApi, setUsingApi] = useState(false);
  const [returnDraft, setReturnDraft] = useState<TaxReturnDraft | null>(null);
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [inboxOpen, setInboxOpen] = useState(false);
  const [researchOpen, setResearchOpen] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const [clientMasterOpen, setClientMasterOpen] = useState(false);
  const [clientMasterFilter, setClientMasterFilter] = useState("");
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

  // Load clients on mount — use real API only if NEXT_PUBLIC_API_URL is explicitly set
  const useRealApi = Boolean(process.env.NEXT_PUBLIC_API_URL);

  useEffect(() => {
    let cancelled = false;

    function toSidebar(data: ApiClient[]): SidebarClient[] {
      return data.map((c) => ({
        id: String(c.id),
        name: c.name,
        meta: `${c.filing_status} \u00b7 ${c.dependents} dep. \u00b7 ${c.tax_year}`,
        status: mapWorkflowStep(c.workflow_step),
        initials: c.name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase(),
        color: hashColor(c.name),
        adults: mockAdults[c.id] || undefined,
      }));
    }

    async function loadClients() {
      // If explicitly configured to use real API, try that first
      if (useRealApi) {
        try {
          const apiData = await api.clients.list();
          if (!cancelled && Array.isArray(apiData) && apiData.length > 0) {
            setUsingApi(true);
            setApiClients(apiData);
            setSidebarClients(toSidebar(apiData));
            setActiveClientId(String(apiData[0].id));
            return;
          }
        } catch {
          // Fall through to mock
        }
      }

      // Use mock data
      try {
        const mockData = await mockApi.clients.list();
        if (!cancelled && mockData.length > 0) {
          setApiClients(mockData);
          setSidebarClients(toSidebar(mockData));
          setActiveClientId(String(mockData[0].id));
        }
      } catch { /* ignore */ }
    }
    loadClients();
    return () => { cancelled = true; };
  }, [setApiClients, useRealApi]);

  // Load chat and documents when active client changes
  useEffect(() => {
    if (!activeClientId) return;
    const numId = Number(activeClientId);
    if (isNaN(numId)) return;

    let cancelled = false;
    async function loadClientData() {
      const source = usingApi ? api : mockApi;
      try {
        const [chatData, docData] = await Promise.all([
          source.chat.history(numId),
          source.documents.list(numId),
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
                hour: "numeric",
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
        setMessages([]);
        setDocuments([]);
      }
    }
    loadClientData();
    return () => { cancelled = true; };
  }, [activeClientId, usingApi, setApiMessages, setApiDocuments]);

  // Send message handler
  const handleSendMessage = useCallback(
    async (content: string) => {
      const newUserMsg: LocalMessage = {
        id: Date.now(),
        role: "user",
        content,
        timestamp: new Date().toLocaleTimeString([], {
          hour: "numeric",
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
                  hour: "numeric",
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

      // Fallback to mock API
      try {
        const response = await mockApi.chat.send(numId, content);
        setIsTyping(false);
        setMessages((prev) => [
          ...prev,
          {
            id: response.id || Date.now() + 1,
            role: "assistant",
            content: response.content,
            timestamp: new Date(response.created_at || Date.now()).toLocaleTimeString([], {
              hour: "numeric",
              minute: "2-digit",
            }),
          },
        ]);
      } catch {
        setIsTyping(false);
      }
    },
    [activeClientId, usingApi]
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
    if (isNaN(numId)) return;
    const source = usingApi ? api : mockApi;
    try {
      const draft = await source.returns.draft(numId);
      setReturnDraft(draft);
    } catch { /* ignore */ }
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
        content: `Uploading **${file.name}** (${formType})...`,
        timestamp: new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, uploadMsg]);

      const numId = Number(activeClientId);
      if (isNaN(numId)) return;

      const source = usingApi ? api : mockApi;
      try {
        const doc = await source.documents.upload(numId, file, formType);
        const docData = await source.documents.list(numId);
        if (Array.isArray(docData)) {
          setDocuments(docData.map((d: ApiDocument) => ({
            ...d, client_id: d.client_id, name: d.title, type: d.form_type,
          })));
        }
        let summary = `**${formType}** uploaded and processed (${Math.round(doc.confidence * 100)}% confidence).`;
        try {
          const data = JSON.parse(doc.extracted_data);
          if (typeof data === "object" && data !== null) {
            const entries = Object.entries(data).slice(0, 4);
            const details = entries.map(([k, v]) => `${k.replace(/_/g, " ")}: ${typeof v === "number" ? `$${v.toLocaleString()}` : v}`).join(" \u00b7 ");
            if (details) summary += `\n${details}`;
          }
        } catch { /* ignore */ }
        const flags = JSON.parse(doc.flags || "[]");
        if (flags.length > 0) {
          summary += `\n\u26A0 ${flags.length} flag(s): ${flags.join(", ")}`;
        }
        setMessages((prev) => [
          ...prev.filter((m) => m.id !== uploadMsg.id),
          { id: Date.now() + 1, role: "assistant" as const, content: summary,
            timestamp: new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) },
        ]);
      } catch (err) {
        setMessages((prev) => [
          ...prev.filter((m) => m.id !== uploadMsg.id),
          { id: Date.now() + 1, role: "assistant" as const,
            content: `Failed to upload ${file.name}: ${err instanceof Error ? err.message : "Unknown error"}`,
            timestamp: new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) },
        ]);
      }
    },
    [activeClientId, usingApi]
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

  const flagCount = documents.filter((d) => d.status === "flagged" || d.status === "pending").length;

  // ── Reusable content blocks ──────────────────────

  const sidebarContent = (
    <ClientSidebar
      clients={sidebarClients}
      activeClientId={activeClientId}
      onSelectClient={handleSelectClient}
      onNewIntake={() => setIntakeOpen(true)}
      onResearchAgent={() => setResearchOpen(true)}
    />
  );

  const workPanelContent = (
    <>
      <Tabs
        tabs={["Documents", "Tax Return", "Filing", "Advisory"]}
        activeTab={activeWorkTab}
        onTabChange={setActiveWorkTab}
        className="px-2 pt-1"
      />

      <div className="flex-1 overflow-y-auto p-3">
        {activeWorkTab === "Documents" && (
          <div className="space-y-3">
            {documents.map((doc) => {
              // Duplicate detection: same form_type with similar extracted data
              const isDuplicate = documents.some(
                (other) =>
                  other.id !== doc.id &&
                  other.form_type === doc.form_type &&
                  other.extracted_data === doc.extracted_data &&
                  other.extracted_data !== "{}"
              );
              return (
                <DocumentCard
                  key={doc.id}
                  doc={doc}
                  onClick={() => { setViewerDoc(doc); setViewerOpen(true); }}
                  onDelete={async (docId) => {
                    const numId = Number(activeClientId);
                    if (isNaN(numId)) return;
                    const source = usingApi ? api : mockApi;
                    try {
                      if (usingApi) {
                        await api.documents.delete(docId);
                      }
                      const docData = await source.documents.list(numId);
                      if (Array.isArray(docData)) {
                        setDocuments(docData.map((d: any) => ({
                          ...d, client_id: d.client_id, name: d.title, type: d.form_type,
                        })));
                      }
                    } catch (err) {
                      console.error("Delete failed:", err);
                    }
                  }}
                  isDuplicate={isDuplicate}
                />
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

        {activeWorkTab === "Filing" && (
          <FilingWorkflow
            clientName={activeClient?.name}
            filingStatus={activeClient?.meta.split(" \u00b7 ")[0]}
          />
        )}

        {activeWorkTab === "Advisory" && (
          <AdvisoryPanel
            clientName={activeClient?.name}
            filingStatus={activeClient?.meta.split(" \u00b7 ")[0]}
            dependents={Number(activeClient?.meta.match(/(\d+) dep/)?.[1] || 0)}
          />
        )}
      </div>
    </>
  );

  const chatContent = (
    <main className="flex-1 flex flex-col bg-surface min-w-0 min-h-0">
      {/* Context bar */}
      <div className="shrink-0 border-b border-divider px-5 py-3 bg-surface-secondary/50">
        {/* Top row: client info + tracking labels */}
        <div className="flex items-center gap-3">
          <div className="flex-1 min-w-0 flex items-center gap-3">
            <span className="text-[16px] font-semibold text-primary tracking-tight">
              {activeClient?.name || "Select a client"}
            </span>
            {activeClient && (
              <>
                <span className="text-[12px] text-secondary hidden md:inline">{activeClient.meta}</span>
                <Badge variant={activeClient.status as "pending" | "inProgress" | "review" | "completed" | "filed"}>
                  {activeClient.status === "pending" ? "Intake" : activeClient.status === "inProgress" ? "Documents" : activeClient.status === "completed" ? "Prepare" : activeClient.status}
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
          <span className="hidden xl:inline text-[12px] font-semibold text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/15 px-2.5 py-1 rounded-md">
            Federal: +$4,820
          </span>
          <span className="hidden xl:inline text-[12px] font-semibold text-primary bg-surface-secondary px-2.5 py-1 rounded-md">
            NJ: -$1,240
          </span>
        </div>

        {/* Second row: workflow stepper — grayscale */}
        <div className="hidden md:flex items-center gap-1 mt-2">
          <span className="text-[11px] text-tertiary mr-1">2025</span>
          {["Intake", "Documents", "Review", "Prepare", "File"].map(
            (step, i) => (
              <div key={step} className="flex items-center gap-1">
                {i > 0 && <div className="w-3 h-px bg-divider" />}
                <span
                  className={cn(
                    "text-[11px] px-2 py-0.5 rounded-full",
                    i < 2
                      ? "text-primary font-medium bg-surface-secondary"
                      : i === 2
                        ? "text-primary font-semibold bg-surface-tertiary"
                        : "text-tertiary"
                  )}
                >
                  {step}
                </span>
              </div>
            )
          )}
        </div>
      </div>

      {/* Chat area — messages scroll, input floats at bottom */}
      <div className="relative flex-1 min-h-0">
        {/* Messages — scroll area fills the container, padding at bottom for input */}
        <MessageList messages={messages} isTyping={isTyping} />

        {/* Floating input at bottom */}
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-surface from-80% to-transparent pt-6">
          <input
            type="file"
            ref={fileInputRef}
            className="hidden"
            accept=".pdf,.png,.jpg,.jpeg,.tiff"
            onChange={handleFileSelected}
          />
          <ChatInput
            onSend={handleSendMessage}
            onAttach={() => fileInputRef.current?.click()}
          />
        </div>
      </div>
    </main>
  );

  // ── Render ─────────────────────────────────────

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <TopBar
        stats={{ clients: totalClients, filed: filedCount, review: reviewCount }}
        deadline="April 15 in 4 days"
        user={{ initials: "SC" }}
        showMenu={!isDesktopXL}
        onMenuToggle={() => setSidebarOpen(!sidebarOpen)}
        clientName={isMobile ? activeClient?.name : undefined}
        onDashboard={() => setDashboardOpen(true)}
        onStatsClick={(filter?: string) => { setClientMasterFilter(filter || ""); setClientMasterOpen(true); }}
        onAvatarClick={() => setSettingsOpen(true)}
        onInbox={() => setInboxOpen(true)}
        inboxUnread={3}
      />

      {isMobile ? (
        /* ── Mobile layout: single panel + bottom tabs ── */
        <>
          <div className="flex-1 overflow-hidden flex flex-col min-h-0">
            {mobileTab === "clients" && (
              <div className="flex-1 overflow-y-auto">{sidebarContent}</div>
            )}
            {mobileTab === "chat" && chatContent}
            {mobileTab === "docs" && (
              <div className="flex-1 overflow-y-auto flex flex-col">{workPanelContent}</div>
            )}
            {mobileTab === "returns" && (
              <div className="flex-1 overflow-y-auto flex flex-col">
                <Tabs
                  tabs={["Tax Return", "Filing", "Advisory"]}
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
                  {activeWorkTab === "Filing" && (
                    <FilingWorkflow
                      clientName={activeClient?.name}
                      filingStatus={activeClient?.meta.split(" \u00b7 ")[0]}
                    />
                  )}
                  {activeWorkTab === "Advisory" && (
                    <AdvisoryPanel
                      clientName={activeClient?.name}
                      filingStatus={activeClient?.meta.split(" \u00b7 ")[0]}
                      dependents={Number(activeClient?.meta.match(/(\d+) dep/)?.[1] || 0)}
                    />
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
        <div className="flex flex-1 overflow-hidden min-h-0">
          {/* Sidebar — inline on lg+, overlay on tablet */}
          <div className="hidden lg:block h-full">{sidebarContent}</div>

          {/* Chat panel */}
          {chatContent}

          {/* Work panel — inline on XL, overlay below */}
          {isDesktopXL && (
            <aside className="w-96 shrink-0 bg-surface border-l border-divider flex flex-col overflow-hidden min-h-0">
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

      <DashboardModal open={dashboardOpen} onClose={() => setDashboardOpen(false)} />
      <ClientMasterModal
        open={clientMasterOpen}
        onClose={() => setClientMasterOpen(false)}
        clients={apiClients}
        initialFilter={clientMasterFilter}
        onSelectClient={(id) => handleSelectClient(String(id))}
      />
      <InboxModal open={inboxOpen} onClose={() => setInboxOpen(false)} />
      <ResearchAgentModal open={researchOpen} onClose={() => setResearchOpen(false)} />

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
                timestamp: new Date(m.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
              })));
            }
            setDocuments([]);
          } catch {
            try {
              const created = await mockApi.clients.create({
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
              handleSelectClient(newId);

              const chatData = await mockApi.chat.history(created.id);
              if (Array.isArray(chatData)) {
                setMessages(chatData.map((m: ChatMessage) => ({
                  id: m.id, role: m.role, content: m.content,
                  timestamp: new Date(m.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
                })));
              }
              setDocuments([]);
            } catch {
              const newId = String(Date.now());
              setSidebarClients((prev) => [
                { id: newId, name, meta: filingLabel, status: "pending", initials: name.slice(0, 2).toUpperCase(), color: "#6B7280" },
                ...prev,
              ]);
              handleSelectClient(newId);
              setMessages([]);
            }
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
