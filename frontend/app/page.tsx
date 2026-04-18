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
import { DocumentManagerModal } from "@/components/documents/document-manager-modal";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Tabs } from "@/components/ui/tabs";
import { api, USE_MOCK } from "@/lib/api-client";
import { useToast } from "@/components/ui/toast";
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
import { ProductTour } from "@/components/onboarding/product-tour";

// ────────────────────────────────────────────
// Page component
// ────────────────────────────────────────────

interface LocalMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  created_at?: string;
}

interface LocalDoc {
  id: string;
  form_type: string;
  title: string;
  status: string;
  confidence: number;
  extracted_data: string;
  flags: string;
  name: string;
  type: string;
  file_name?: string;
  created_at?: string;
  created_by_name?: string | null;
  reviewed_at?: string | null;
  reviewed_by_name?: string | null;
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
  const { toast } = useToast();
  const [returnDraft, setReturnDraft] = useState<TaxReturnDraft | null>(null);
  const [workflowSteps, setWorkflowSteps] = useState<Array<{ id: string; label: string; complete: boolean; can_complete?: boolean }>>([]);
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [intakeMode, setIntakeMode] = useState<"create" | "edit">("create");
  const [intakeEditData, setIntakeEditData] = useState<
    Partial<IntakeFormData> & {
      id?: string;
      ssnMasked?: string;
      dobMasked?: string;
      spouseSsnMasked?: string;
      spouseDobMasked?: string;
      streetMasked?: string;
    } | undefined
  >();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [inboxOpen, setInboxOpen] = useState(false);
  const [researchOpen, setResearchOpen] = useState(false);
  const [showProductTour, setShowProductTour] = useState(false);
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const [docManagerOpen, setDocManagerOpen] = useState(false);
  const [clientDependents, setClientDependents] = useState<Array<{id: string; first_name: string; last_name: string; relationship: string; ssn_masked?: string}>>([]);
  const [clientMasterOpen, setClientMasterOpen] = useState(false);
  const [clientMasterFilter, setClientMasterFilter] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isMobile = useIsMobile();
  const isDesktopXL = useIsDesktopXL();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [workPanelOpen, setWorkPanelOpen] = useState(false);
  const [mobileTab, setMobileTab] = useState<TabId>("chat");

  const activeClient = sidebarClients.find((c) => c.id === activeClientId);

  // Refresh a single client's data (workflow, return draft, etc.) after state-changing actions
  const refreshActiveClient = useCallback(async () => {
    const cid = activeClientId;
    if (!cid) return;
    try {
      const [updated, draft, workflow] = await Promise.all([
        api.clients.get(cid),
        api.returns.get(cid).catch(() => null),
        api.clients.getWorkflow(cid).catch(() => null),
      ]);
      if (updated) {
        setApiClients((prev) => prev.map((c) => (c.id === cid ? updated : c)));
        setSidebarClients((prev) =>
          prev.map((c) =>
            c.id === cid
              ? {
                  ...c,
                  status: updated.workflow_step,
                  meta: `${updated.filing_status} \u00b7 ${updated.dependents} dep. \u00b7 ${updated.tax_year}`,
                  adults: deriveAdults(updated),
                }
              : c
          )
        );
      }
      if (draft) setReturnDraft(draft);
      if (workflow?.steps) setWorkflowSteps(workflow.steps);
    } catch {
      // Non-critical — UI will update on next full refresh
    }
  }, [activeClientId, setApiClients]);

  // Check onboarding on mount
  useEffect(() => {
    if (!localStorage.getItem("taxflow_product_tour_complete")) {
      setShowProductTour(true);
    }
  }, []);

  const completeProductTour = useCallback(() => {
    localStorage.setItem("taxflow_product_tour_complete", "true");
    setShowProductTour(false);
  }, []);

  const replayTour = useCallback(() => {
    setSettingsOpen(false);
    localStorage.removeItem("taxflow_product_tour_complete");
    setShowProductTour(true);
  }, []);

  // Load clients on mount. The `api` object is whichever implementation
  // (real or mock) was selected at module load via NEXT_PUBLIC_USE_MOCK_DATA.
  // No silent fallback — backend errors surface as toasts so failures are
  // visible instead of being papered over with stale mock data.
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
        adults: deriveAdults(c),
      }));
    }

    async function loadClients() {
      try {
        const data = await api.clients.list();
        if (cancelled || !Array.isArray(data)) return;
        setApiClients(data);
        setSidebarClients(toSidebar(data));
        if (data.length > 0) setActiveClientId(String(data[0].id));
      } catch (err) {
        if (cancelled) return;
        toast(
          "error",
          "Failed to load clients",
          err instanceof Error ? err.message : "Unknown error",
        );
      }
    }
    loadClients();
    return () => { cancelled = true; };
  }, [setApiClients, toast]);

  // Load chat and documents when active client changes
  useEffect(() => {
    if (!activeClientId) return;
    const cid = activeClientId;
    if (!cid) return;

    let cancelled = false;
    async function loadClientData() {
      try {
        const [chatData, docData, workflowData] = await Promise.all([
          api.chat.history(cid),
          api.documents.list(cid),
          api.clients.getWorkflow(cid).catch(() => null),
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
        if (workflowData?.steps) setWorkflowSteps(workflowData.steps);
      } catch {
        setMessages([]);
        setDocuments([]);
      }
    }
    loadClientData();
    return () => { cancelled = true; };
  }, [activeClientId, setApiMessages, setApiDocuments]);

  // Auto-load draft when switching to Tax Return tab
  useEffect(() => {
    if (activeWorkTab !== "Tax Return") return;
    const cid = activeClientId;
    if (!cid) return;
    api.returns.get(cid).then((draft) => {
      if (draft) setReturnDraft(draft);
    });
  }, [activeWorkTab, activeClientId, documents.length]);

  // Send message handler — all messages (chips + free text) go to the agent
  const handleSendMessage = useCallback(
    async (content: string) => {
      const newUserMsg: LocalMessage = {
        id: `m-${Date.now()}`,
        role: "user",
        content,
        timestamp: new Date().toLocaleTimeString([], {
          hour: "numeric",
          minute: "2-digit",
        }),
      };
      setMessages((prev) => [...prev, newUserMsg]);
      setIsTyping(true);

      const cid = activeClientId;
      if (!cid) {
        setIsTyping(false);
        setMessages((prev) => [
          ...prev,
          {
            id: `m-${Date.now()}-no-client`,
            role: "assistant" as const,
            content:
              "No client is currently selected. To get started:\n\n" +
              "1. **Create a new client** using the **+ New Intake** button in the sidebar\n" +
              "2. **Select an existing client** from the sidebar\n\n" +
              "Once a client is selected, I can help you with their tax return, documents, and advisory work.",
            timestamp: new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
          },
        ]);
        return;
      }

      try {
        const response = await api.chat.send(cid, content);
        setIsTyping(false);
        // Agent may have triggered workflow changes (compute, approve) via tools
        refreshActiveClient();
        if (response && response.content) {
          setMessages((prev) => [
            ...prev,
            {
              id: response.id || `m-${Date.now()}-r`,
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
      } catch (err) {
        setIsTyping(false);
        toast(
          "error",
          "Chat request failed",
          err instanceof Error ? err.message : "Backend unavailable",
        );
      }
    },
    [activeClientId, toast, refreshActiveClient]
  );

  // Document approve handler
  const handleApproveDoc = useCallback(
    async (docId: string) => {
      // Round-trip through the API and merge the *response* back into local
      // state. The backend stamps ``reviewed_by`` / ``reviewed_at`` and
      // sets ``status='approved'``; if we instead just locally flipped the
      // status to "verified" (the previous behavior) the chip's audit-trail
      // line was permanently wrong until the next full list-refetch.
      let updated;
      try {
        updated = await api.documents.approve(docId);
      } catch {
        return;
      }
      setDocuments((prev) =>
        prev.map((d) =>
          d.id === docId
            ? {
                ...d,
                status: updated.status,
                reviewed_at: updated.reviewed_at,
                reviewed_by: updated.reviewed_by,
                reviewed_by_name: updated.reviewed_by_name,
              }
            : d,
        ),
      );
      // Approval may advance workflow (documents → review)
      refreshActiveClient();
    },
    [refreshActiveClient]
  );

  // Generate return draft
  const handleGenerateReturn = useCallback(async () => {
    const cid = activeClientId;
    if (!cid) return;
    const source = api;
    try {
      const draft = await api.returns.draft(cid);
      setReturnDraft(draft);
      // Compute advances workflow (review → filing)
      refreshActiveClient();
    } catch { /* ignore */ }
  }, [activeClientId, refreshActiveClient]);

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
        id: `m-${Date.now()}`,
        role: "assistant",
        content: `Uploading **${file.name}** (${formType})...`,
        timestamp: new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, uploadMsg]);

      const cid = activeClientId;
      if (!cid) return;

      try {
        const doc = await api.documents.upload(cid, file, formType);
        // Upload advances workflow (intake → documents)
        refreshActiveClient();
        const docData = await api.documents.list(cid);
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
          { id: `m-${Date.now()}-1`, role: "assistant" as const, content: summary,
            timestamp: new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) },
        ]);
      } catch (err) {
        setMessages((prev) => [
          ...prev.filter((m) => m.id !== uploadMsg.id),
          { id: `m-${Date.now()}-1`, role: "assistant" as const,
            content: `Failed to upload ${file.name}: ${err instanceof Error ? err.message : "Unknown error"}`,
            timestamp: new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) },
        ]);
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

  const flagCount = documents.filter((d) => d.status === "flagged" || d.status === "pending").length;

  // ── Reusable content blocks ──────────────────────

  const sidebarContent = (
    <ClientSidebar
      clients={sidebarClients}
      activeClientId={activeClientId}
      onSelectClient={handleSelectClient}
      onNewIntake={() => { setIntakeMode("create"); setIntakeEditData(undefined); setIntakeOpen(true); }}
      onResearchAgent={() => setResearchOpen(true)}
      onEditClient={(clientId) => {
        const cid = clientId;
        const c = apiClients.find((cl) => cl.id === cid);
        if (!c) return;
        // Mask-by-default policy: PII fields stay empty in the form. The
        // masked snippets (***-**-1234, **/**/1985, etc.) are passed through
        // as `*Masked` props so PiiInput can show the snippet as a
        // placeholder + render the eye-toggle reveal button (gated by
        // can_view_pii on the user's session). This avoids leaking PII onto
        // the screen during screen-share / over-the-shoulder scenarios.
        setIntakeEditData(clientToFormData(c));
        setIntakeMode("edit");
        setIntakeOpen(true);
      }}
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
                    const cid = activeClientId;
                    if (!cid) return;
                    try {
                      await api.documents.delete(docId);
                      const docData = await api.documents.list(cid);
                      if (Array.isArray(docData)) {
                        setDocuments(docData.map((d: any) => ({
                          ...d, client_id: d.client_id, name: d.title, type: d.form_type,
                        })));
                      }
                      // Deletion may roll back workflow step
                      refreshActiveClient();
                    } catch (err) {
                      console.error("Delete failed:", err);
                    }
                  }}
                  isDuplicate={isDuplicate}
                />
              );
            })}
            {/* Manage Documents button */}
            <button
              onClick={async () => {
                // Load dependents for the document manager
                const cid = activeClientId;
                if (!!cid) {
                  try {
                    setClientDependents(await api.dependents.list(cid));
                  } catch { /* ignore */ }
                }
                setDocManagerOpen(true);
              }}
              className="w-full mt-2 py-2 text-[12px] text-apple-blue hover:bg-surface-secondary rounded-lg border border-dashed border-divider hover:border-apple-blue/40 transition-all cursor-pointer"
            >
              Manage Documents
            </button>
          </div>
        )}

        {activeWorkTab === "Tax Return" && (
          <>
          <ReturnPreview
            lines={returnDraft?.lines}
            totalIncome={returnDraft?.total_income}
            totalDeductions={returnDraft?.total_deductions}
            taxableIncome={returnDraft?.taxable_income}
            totalTax={returnDraft?.total_tax}
            totalPayments={returnDraft?.total_payments}
            refundOrOwed={returnDraft?.refund_or_owed}
            effectiveRate={returnDraft?.effective_rate}
            computedAt={returnDraft?.computed_at}
            onViewFull={handleGenerateReturn}
          />
          </>
        )}

        {activeWorkTab === "Filing" && (
          <>
          <FilingWorkflow
            clientName={activeClient?.name}
            filingStatus={activeClient?.meta.split(" \u00b7 ")[0]}
          />
          </>
        )}

        {activeWorkTab === "Advisory" && (
          <AdvisoryPanel
            clientId={activeClientId}
            clientName={activeClient?.name}
            filingStatus={activeClient?.meta.split(" \u00b7 ")[0]}
            dependents={Number(activeClient?.meta.match(/(\d+) dep/)?.[1] || 0)}
          />
        )}
      </div>

      {/* Floating workflow action — always visible at bottom of right panel */}
      {(() => {
        const tabToStep: Record<string, string> = {
          "Documents": "documents",
          "Tax Return": "tax_return",
          "Filing": "filed",
        };
        const stepId = tabToStep[activeWorkTab];
        if (!stepId) return null;
        const step = workflowSteps.find((s) => s.id === stepId);
        if (!step) return null;

        const labels: Record<string, string> = {
          documents: "Documents",
          tax_return: "Tax Return",
          filed: "Filed",
        };
        const label = labels[stepId] || stepId;

        if (step.complete) {
          return (
            <div className="shrink-0 border-t border-divider px-3 py-2.5">
              <div className="group flex items-center justify-center gap-1.5 py-2 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-400 text-[12px] font-semibold">
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}><path d="M4.5 12.75l6 6 9-13.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
                {label} Complete
                <button
                  onClick={async () => { const cid = activeClientId; if (cid) { await api.clients.incompleteStep(cid, stepId); refreshActiveClient(); } }}
                  className="ml-1 opacity-0 group-hover:opacity-100 text-[10px] text-tertiary hover:text-red-500 transition-all cursor-pointer"
                  title="Mark incomplete"
                >&times;</button>
              </div>
            </div>
          );
        }
        return (
          <div className="shrink-0 border-t border-divider px-3 py-2.5">
            <button
              onClick={async () => { const cid = activeClientId; if (cid) { await api.clients.completeStep(cid, stepId); refreshActiveClient(); } }}
              disabled={!step.can_complete}
              className="w-full py-2 text-[12px] font-medium text-apple-blue hover:bg-apple-blue/5 rounded-lg border border-apple-blue/30 hover:border-apple-blue transition-all cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Mark {label} Complete
            </button>
          </div>
        );
      })()}
    </>
  );

  const chatContent = (
    <main className="flex-1 flex flex-col bg-surface min-w-0 min-h-0">
      {/* Context bar */}
      <div className="shrink-0 border-b border-divider px-5 py-3 bg-surface-secondary/50">
        {/* Top row: client info + tracking labels */}
        <div className="flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3">
              <span className="text-[16px] font-semibold text-primary tracking-tight">
                {activeClient?.name || "Select a client"}
              </span>
            </div>
            {activeClient?.adults && (
              <div className="text-[12px] text-secondary mt-0.5">{activeClient.adults}</div>
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

          {/* Federal + State refund/owed — always visible, placeholder when not computed */}
          {activeClient && (
            <div className="hidden md:flex items-center gap-2 shrink-0">
              {returnDraft && returnDraft.refund_or_owed !== undefined ? (
                <span className={cn(
                  "text-[12px] font-semibold px-2.5 py-1 rounded-md",
                  returnDraft.refund_or_owed >= 0
                    ? "text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/15"
                    : "text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/15"
                )}>
                  Federal: {returnDraft.refund_or_owed >= 0 ? "+" : ""}${returnDraft.refund_or_owed.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                </span>
              ) : (
                <span className="text-[12px] font-medium text-tertiary px-2.5 py-1 rounded-md bg-surface-secondary">
                  Federal: --
                </span>
              )}
              <span className="text-[12px] font-medium text-tertiary px-2.5 py-1 rounded-md bg-surface-secondary">
                State: --
              </span>
            </div>
          )}
        </div>

        {/* Second row: workflow stepper — green for complete, gray for incomplete */}
        {activeClient && workflowSteps.length > 0 && (() => {
          const clientYear = activeClient.meta.match(/\d{4}/)?.[0] || "2025";
          return (
            <div className="hidden md:flex items-center gap-1 mt-2">
              <span className="text-[11px] text-tertiary mr-1">{clientYear}</span>
              {workflowSteps.map((step, i) => (
                <div key={step.id} className="flex items-center gap-1">
                  {i > 0 && <div className={cn("w-3 h-px", step.complete ? "bg-emerald-400/40" : "bg-divider")} />}
                  <span
                    className={cn(
                      "text-[11px] px-2 py-0.5 rounded-full",
                      step.complete
                        ? "text-emerald-600 dark:text-emerald-400 font-semibold bg-gray-50 dark:bg-emerald-950/20"
                        : "text-tertiary"
                    )}
                  >
                    {step.label}
                  </span>
                </div>
              ))}
            </div>
          );
        })()}
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
          <ChatInput onSend={handleSendMessage} />
        </div>
      </div>
    </main>
  );

  // ── Render ─────────────────────────────────────

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <TopBar
        stats={{ clients: totalClients, filed: filedCount, review: reviewCount }}
        deadline=""
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
                      lines={returnDraft?.lines}
                      totalIncome={returnDraft?.total_income}
                      totalDeductions={returnDraft?.total_deductions}
                      taxableIncome={returnDraft?.taxable_income}
                      totalTax={returnDraft?.total_tax}
                      totalPayments={returnDraft?.total_payments}
                      refundOrOwed={returnDraft?.refund_or_owed}
                      effectiveRate={returnDraft?.effective_rate}
                      computedAt={returnDraft?.computed_at}
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
                      clientId={activeClientId}
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

      {/* Document Manager modal */}
      <DocumentManagerModal
        open={docManagerOpen}
        onClose={() => setDocManagerOpen(false)}
        client={(() => {
          const cid = activeClientId;
          const c = apiClients.find((c) => c.id === cid);
          if (!c) return null;
          return {
            name: c.name,
            filing_status: c.filing_status,
            tax_year: c.tax_year,
            dependents: c.dependents,
            ...(c as any),
          };
        })()}
        dependents={clientDependents}
        documents={documents}
        onUpload={async (files) => {
          const cid = activeClientId;
          if (!cid) return;
              for (const file of files) {
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
            try {
              await api.documents.upload(cid, file, formType);
            } catch (err) {
              console.error(`Upload failed for ${file.name}:`, err);
            }
          }
          // Refresh document list
          try {
            const docData = await api.documents.list(cid);
            if (Array.isArray(docData)) {
              setDocuments(docData.map((d: any) => ({
                ...d, client_id: d.client_id, name: d.title, type: d.form_type,
              })));
            }
          } catch { /* ignore */ }
        }}
        onDelete={async (docId) => {
          const cid = activeClientId;
          if (!cid) return;
          try {
            await api.documents.delete(docId);
            const docData = await api.documents.list(cid);
            if (Array.isArray(docData)) {
              setDocuments(docData.map((d: any) => ({
                ...d, client_id: d.client_id, name: d.title, type: d.form_type,
              })));
            }
            refreshActiveClient();
          } catch (err) {
            console.error("Delete failed:", err);
          }
        }}
        onApprove={async (docId) => {
          try {
            await api.documents.approve(docId);
            setDocuments((prev) =>
              prev.map((d) => (d.id === docId ? { ...d, status: "approved" } : d))
            );
          } catch (err) {
            console.error("Approve failed:", err);
          }
        }}
        onViewDoc={(doc) => {
          setViewerDoc(doc);
          setViewerOpen(true);
        }}
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

      <ProductTour
        active={showProductTour}
        onComplete={completeProductTour}
      />

      <IntakeModal
        open={intakeOpen}
        onClose={() => { setIntakeOpen(false); setIntakeMode("create"); setIntakeEditData(undefined); }}
        mode={intakeMode}
        editData={intakeEditData}
        onSubmit={async (data: IntakeFormData) => {
          // Throws on failure — IntakeModal catches and shows inline error.
          // No silent fallbacks; no mock retries; no document upload.
          // Display name uses a consistent "First Last" format. Earlier
          // versions wrote "Last, First" which round-tripped badly (every
          // edit mangled the format further).
          const name = data.familyGroupName
            ? data.familyGroupName
            : `${data.firstName.trim()} ${data.lastName.trim()}`.trim();

          const payload = {
            name,
            primary_first_name: data.firstName.trim() || undefined,
            primary_last_name: data.lastName.trim() || undefined,
            filing_status: data.filingStatus,
            tax_year: data.taxYear,
            dependents: data.dependents,
            primary_ssn: data.ssn || undefined,
            primary_dob: data.dateOfBirth || undefined,
            email: data.email || undefined,
            phone: data.phone || undefined,
            spouse_first_name: data.spouseFirstName || undefined,
            spouse_last_name: data.spouseLastName || undefined,
            spouse_ssn: data.spouseSsn || undefined,
            spouse_dob: data.spouseDob || undefined,
            spouse_email: data.spouseEmail || undefined,
            spouse_phone: data.spousePhone || undefined,
            street: data.street || undefined,
            city: data.city || undefined,
            state: data.state || undefined,
            zip_code: data.zip || undefined,
            family_group_name: data.familyGroupName || undefined,
            filing_federal: data.filingFederal,
            filing_states: data.filingStates ?? [],
          };

          let clientId: string;
          if (intakeMode === "edit" && intakeEditData?.id) {
            const updated = await api.clients.update(intakeEditData.id, payload);
            clientId = updated.id;
          } else {
            const created = await api.clients.create(payload);
            clientId = created.id;
          }

          // Persist dependents (best-effort: a failure here surfaces as a
          // toast but doesn't roll back the client save).
          for (const dep of data.dependentDetails) {
            if (!dep.firstName.trim()) continue;
            await api.dependents.create(clientId, {
              first_name: dep.firstName,
              last_name: dep.lastName,
              ssn: dep.ssn || undefined,
              date_of_birth: dep.dob || undefined,
              relationship: dep.relationship,
            });
          }

          // Refresh sidebar so the new/updated client shows immediately.
          const apiData = await api.clients.list();
          if (Array.isArray(apiData)) {
            setApiClients(apiData);
            setSidebarClients(apiData.map((c) => ({
              id: String(c.id),
              name: c.name,
              meta: `${c.filing_status} \u00b7 ${c.dependents} dep. \u00b7 ${c.tax_year}`,
              status: mapWorkflowStep(c.workflow_step),
              initials: c.name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase(),
              color: hashColor(c.name),
              adults: deriveAdults(c),
            })));
          }
          setActiveClientId(String(clientId));
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
  // Pass through directly — sidebar now uses the raw step ID
  return step || "intake";
}

/**
 * Map a server `Client` (snake_case, masked PII) onto the intake form's
 * `IntakeFormData` shape (camelCase, plaintext fields). Crucial for edit:
 *
 *   - Splits ``name`` into first/last on either "Last, First" or "First Last"
 *     so the value round-trips cleanly with the new "First Last" save format.
 *   - Blanks out values that look masked ("***-**-1234") because the form
 *     can't display them as real values; sending them back would corrupt
 *     the encrypted column. User must re-type sensitive PII to change it.
 *   - Date inputs cleared too — masked DOBs cannot bind to a date input.
 */
/**
 * Build the "adult names" line that appears under each client in the sidebar
 * (e.g. "John Doe" or "John & Jane Doe"). Derived purely from REAL backend
 * data — no mock map keyed on client id (the previous implementation showed
 * "Marcus Williams" for any client that happened to land at id=6).
 */
function deriveAdults(c: ApiClient): string | undefined {
  const first = (c.primary_first_name || "").trim();
  const last = (c.primary_last_name || "").trim();
  const sFirst = (c.spouse_first_name || "").trim();
  const sLast = (c.spouse_last_name || "").trim();
  const primary = `${first} ${last}`.trim();
  if (sFirst || sLast) {
    const spouse = `${sFirst} ${sLast}`.trim();
    if (primary && spouse) return `${first || primary} & ${spouse}`;
    return primary || spouse || undefined;
  }
  return primary || undefined;
}

function clientToFormData(
  c: ApiClient,
): Partial<IntakeFormData> & {
  id: string;
  ssnMasked?: string;
  dobMasked?: string;
  spouseSsnMasked?: string;
  spouseDobMasked?: string;
  streetMasked?: string;
} {
  // Prefer the dedicated columns (added later — they round-trip cleanly).
  // Fall back to a name-split heuristic ONLY for legacy rows created before
  // the columns existed (where they may still be NULL).
  let firstName = c.primary_first_name || "";
  let lastName = c.primary_last_name || "";
  if (!firstName && !lastName) {
    const name = (c.name || "").trim();
    if (name.includes(",")) {
      const [last, ...rest] = name.split(",");
      lastName = last.trim();
      firstName = rest.join(",").trim();
    } else {
      const parts = name.split(/\s+/);
      firstName = parts[0] || "";
      lastName = parts.slice(1).join(" ");
    }
  }

  // PII fields (SSN, DOB, street) are intentionally returned as empty
  // strings — PiiInput renders the masked snippet as a placeholder and
  // exposes an eye-toggle to fetch the plaintext on demand. This keeps
  // sensitive values off the screen by default.
  return {
    id: c.id,
    firstName,
    lastName,
    ssn: "",
    ssnMasked: c.primary_ssn_masked || "",
    dateOfBirth: "",
    dobMasked: c.primary_dob_masked || "",
    email: c.email || "",
    phone: c.phone || "",
    spouseFirstName: c.spouse_first_name || "",
    spouseLastName: c.spouse_last_name || "",
    spouseSsn: "",
    spouseSsnMasked: c.spouse_ssn_masked || "",
    spouseDob: "",
    spouseDobMasked: c.spouse_dob_masked || "",
    spouseEmail: c.spouse_email || "",
    spousePhone: c.spouse_phone || "",
    filingStatus: c.filing_status,
    taxYear: c.tax_year,
    dependents: c.dependents,
    street: "",
    streetMasked: c.street_masked || "",
    city: c.city || "",
    state: c.state || "",
    zip: c.zip_code || "",
    familyGroupName: c.family_group_name || "",
    filingFederal: c.filing_federal ?? true,
    filingStates: c.filing_states ?? [],
  };
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
