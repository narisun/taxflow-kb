"use client";

import { useState, useRef, useCallback, useEffect, KeyboardEvent } from "react";
import { Modal } from "@/components/ui/modal";
import { cn, fmtTime, deriveInitials } from "@/lib/utils";
import { useTimezone, useMeOrNull } from "@/components/auth/me-context";
import { api } from "@/lib/api-client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface ResearchAgentModalProps {
  open: boolean;
  onClose: () => void;
}

interface ResearchMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

interface ResearchThread {
  id: string;
  title: string;
  conversation_type: string;
  created_at: string;
  updated_at: string;
}

interface ResearchStep {
  tool: string;
  description: string;
  summary?: string;
  status: "running" | "complete";
}

export function ResearchAgentModal({ open, onClose }: ResearchAgentModalProps) {
  const tz = useTimezone();
  const me = useMeOrNull();
  const userInitials = deriveInitials(me?.user?.name, me?.user?.email);

  const [threads, setThreads] = useState<ResearchThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ResearchMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [researchSteps, setResearchSteps] = useState<ResearchStep[]>([]);
  const [stepsCollapsed, setStepsCollapsed] = useState(false);
  const [loadingThreads, setLoadingThreads] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const lastMsgCount = useRef(0);

  // Load threads on mount
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoadingThreads(true);
    setError(null);
    api.research
      .listThreads()
      .then((res) => {
        if (cancelled) return;
        setThreads(res.items);
        if (res.items.length > 0 && !activeThreadId) {
          setActiveThreadId(res.items[0].id);
        }
      })
      .catch((err) => { if (!cancelled) setError(err.message || "Failed to load threads"); })
      .finally(() => { if (!cancelled) setLoadingThreads(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Load messages when active thread changes
  useEffect(() => {
    if (!activeThreadId) { setMessages([]); return; }
    let cancelled = false;
    setLoadingMessages(true);
    setError(null);
    setResearchSteps([]);
    setStepsCollapsed(false);
    api.research
      .getMessages(activeThreadId)
      .then((res) => {
        if (cancelled) return;
        setMessages(res.messages.map((m) => ({
          id: m.id,
          role: m.role as "user" | "assistant",
          content: m.content,
          created_at: m.created_at,
        })));
      })
      .catch((err) => { if (!cancelled) setError(err.message || "Failed to load messages"); })
      .finally(() => { if (!cancelled) setLoadingMessages(false); });
    return () => { cancelled = true; };
  }, [activeThreadId]);

  // Scroll to bottom
  useEffect(() => {
    const count = messages.length;
    const isInitial = lastMsgCount.current === 0 && count > 0;
    lastMsgCount.current = count;
    if (isInitial) {
      messagesEndRef.current?.scrollIntoView();
    } else {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages.length, isStreaming, researchSteps.length]);

  // Auto-create thread and send first message
  const sendMessage = useCallback(async (content: string, threadId: string) => {
    setError(null);
    const userMsg: ResearchMessage = {
      id: `temp-${Date.now()}`,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsStreaming(true);
    setResearchSteps([]);
    setStepsCollapsed(false);

    const assistantMsgId = `stream-${Date.now()}`;
    let assistantAdded = false;

    try {
      const response = await api.research.sendMessage(threadId, content);
      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response stream");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmedLine = line.trim();
          if (!trimmedLine.startsWith("data:")) continue;
          const jsonStr = trimmedLine.slice(5).trim();
          if (!jsonStr || jsonStr === "[DONE]") continue;

          try {
            const payload = JSON.parse(jsonStr);
            const eventType = payload.type || payload.event;
            if (eventType === "step_start") {
              setResearchSteps((prev) => [...prev, { tool: payload.tool, description: payload.description, status: "running" }]);
            } else if (eventType === "step_complete") {
              setResearchSteps((prev) => prev.map((s) => s.tool === payload.tool && s.status === "running" ? { ...s, status: "complete", summary: payload.summary } : s));
            } else if (eventType === "text_delta") {
              if (!assistantAdded) {
                assistantAdded = true;
                setMessages((prev) => [...prev, { id: assistantMsgId, role: "assistant", content: payload.text ?? "", created_at: new Date().toISOString() }]);
              } else {
                setMessages((prev) => prev.map((m) => m.id === assistantMsgId ? { ...m, content: m.content + (payload.text ?? "") } : m));
              }
            } else if (eventType === "done") {
              setStepsCollapsed(true);
            } else if (eventType === "error") {
              setError(payload.message || "Stream error");
            }
          } catch { /* skip malformed */ }
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to send message");
      if (assistantAdded) {
        setMessages((prev) => prev.filter((m) => m.id !== assistantMsgId || m.content.length > 0));
      }
    } finally {
      setIsStreaming(false);
    }
  }, []);

  const handleSend = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    // Auto-create thread if none active
    let threadId = activeThreadId;
    if (!threadId) {
      try {
        const thread = await api.research.createThread();
        setThreads((prev) => [thread, ...prev]);
        setActiveThreadId(thread.id);
        threadId = thread.id;
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Failed to create thread");
        return;
      }
    }

    sendMessage(trimmed, threadId);
  }, [input, activeThreadId, isStreaming, sendMessage]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  };

  const handleNewThread = async () => {
    setError(null);
    try {
      const thread = await api.research.createThread();
      setThreads((prev) => [thread, ...prev]);
      setActiveThreadId(thread.id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create thread");
    }
  };

  const handleDeleteThread = async (threadId: string) => {
    setError(null);
    try {
      await api.research.deleteThread(threadId);
      setThreads((prev) => prev.filter((t) => t.id !== threadId));
      if (activeThreadId === threadId) {
        setActiveThreadId(threads.find((t) => t.id !== threadId)?.id ?? null);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to delete thread");
    }
  };

  const researchHints = ["IRS filing deadlines", "Section 199A deduction", "Home office rules", "Capital gains rates"];

  return (
    <Modal open={open} onClose={onClose} className="max-w-7xl w-[95vw]">
      <div className="flex h-[85vh]">
        {/* Left: Thread list */}
        <div className="w-64 shrink-0 border-r border-divider flex flex-col bg-bg">
          <div className="flex items-center justify-between px-4 py-3 border-b border-divider">
            <span className="text-[13px] font-semibold text-primary">Research</span>
            <button
              onClick={handleNewThread}
              className="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium text-secondary border border-divider bg-surface hover:bg-surface-secondary transition-colors cursor-pointer"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
                <path d="M12 4.5v15m7.5-7.5h-15" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              New
            </button>
          </div>

          <div className="flex-1 overflow-y-auto scroll-visible">
            {loadingThreads && (
              <div className="flex items-center justify-center py-8">
                <div className="w-5 h-5 border-2 border-apple-blue border-t-transparent rounded-full animate-spin" />
              </div>
            )}
            {!loadingThreads && threads.length === 0 && (
              <div className="px-4 py-8 text-center text-[11px] text-tertiary">
                Start typing below to begin your first research thread.
              </div>
            )}
            {threads.map((thread) => (
              <div
                key={thread.id}
                onClick={() => setActiveThreadId(String(thread.id))}
                className={cn(
                  "group px-4 py-3 border-b border-divider cursor-pointer transition-colors",
                  activeThreadId === thread.id ? "bg-apple-blue/10" : "hover:bg-surface-secondary"
                )}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <span className={cn(
                    "text-[12px] truncate",
                    activeThreadId === thread.id ? "font-semibold text-apple-blue" : "font-medium text-primary"
                  )} title={thread.title}>
                    {thread.title}
                  </span>
                  <div className="flex items-center gap-1 shrink-0 ml-2">
                    <span className="text-[10px] text-tertiary">
                      {fmtTime(thread.updated_at || thread.created_at, tz)}
                    </span>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDeleteThread(thread.id); }}
                      className="hidden group-hover:block text-[10px] text-tertiary hover:text-red-500 cursor-pointer"
                      title="Delete thread"
                    >&times;</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Chat area */}
        <div className="flex-1 flex flex-col min-w-0 bg-surface">
          {/* Header with close button */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-divider shrink-0">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md flex items-center justify-center text-white text-[10px] font-bold shrink-0" style={{ background: "#6B8BA4" }}>R</div>
              <span className="text-[13px] font-semibold text-primary">
                {threads.find((t) => t.id === activeThreadId)?.title || "Research Agent"}
              </span>
            </div>
            <button onClick={onClose} className="w-7 h-7 rounded-lg flex items-center justify-center text-secondary hover:text-primary hover:bg-surface-secondary transition-colors cursor-pointer" aria-label="Close">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                <path d="M6 18L18 6M6 6l12 12" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>

          {/* Error banner */}
          {error && (
            <div className="px-4 py-2 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-[12px] border-b border-divider flex items-center justify-between shrink-0">
              <span>{error}</span>
              <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600 cursor-pointer">&times;</button>
            </div>
          )}

          {/* Messages area */}
          <div className="flex-1 overflow-y-auto scroll-visible relative">
            <div className="px-5 pb-4 flex flex-col min-h-full">
              {loadingMessages ? (
                <div className="flex items-center justify-center flex-1">
                  <div className="w-5 h-5 border-2 border-apple-blue border-t-transparent rounded-full animate-spin" />
                </div>
              ) : messages.length === 0 ? (
                /* Welcome message — same style as main chat */
                <div className="flex flex-col items-center justify-center flex-1 text-tertiary">
                  <div className="w-10 h-10 rounded-md flex items-center justify-center text-white text-[16px] font-bold mb-3" style={{ background: "#6B8BA4" }}>R</div>
                  <p className="text-[14px] font-medium text-secondary mb-1">Research Agent</p>
                  <p className="text-[12px] text-tertiary text-center max-w-[320px] leading-relaxed">
                    Ask tax research questions. I&apos;ll search IRS publications, tax code, and regulations to give you sourced answers.
                  </p>
                </div>
              ) : (
                <>
                  <div className="flex-1" />
                  <div className="space-y-4 py-4">
                    {messages.map((msg, idx) => {
                      const isLastAssistant = msg.role === "assistant" && idx === messages.length - 1 && researchSteps.length > 0;

                      return (
                        <div key={msg.id}>
                          {/* Research steps */}
                          {isLastAssistant && (
                            <div className="mb-3 ml-10">
                              <button
                                onClick={() => setStepsCollapsed((prev) => !prev)}
                                className="flex items-center gap-1.5 text-[11px] font-medium text-secondary mb-1.5 cursor-pointer hover:text-primary transition-colors"
                              >
                                <svg className={cn("w-3 h-3 transition-transform", stepsCollapsed ? "" : "rotate-90")} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                                  <path d="M9 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" />
                                </svg>
                                Research steps ({researchSteps.length})
                              </button>
                              {!stepsCollapsed && (
                                <div className="space-y-1 pl-1">
                                  {researchSteps.map((step, i) => (
                                    <div key={`${step.tool}-${i}`} className="flex items-start gap-2 text-[11px] text-secondary bg-surface-secondary rounded-md px-2.5 py-1.5">
                                      {step.status === "running" ? (
                                        <div className="w-3.5 h-3.5 border-[1.5px] border-apple-blue border-t-transparent rounded-full animate-spin shrink-0 mt-0.5" />
                                      ) : (
                                        <svg className="w-3.5 h-3.5 text-brand-green shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
                                          <path d="M4.5 12.75l6 6 9-13.5" strokeLinecap="round" strokeLinejoin="round" />
                                        </svg>
                                      )}
                                      <div>
                                        <span>{step.description}</span>
                                        {step.summary && <span className="text-tertiary ml-1">— {step.summary}</span>}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}

                          {/* Message bubble — matches main chat style */}
                          <div className={`flex gap-2.5 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                            {msg.role === "assistant" && (
                              <div className="w-7 h-7 rounded-md flex items-center justify-center text-white text-[12px] font-bold shrink-0 mt-0.5" style={{ background: "#6B8BA4" }}>R</div>
                            )}
                            <div className={`flex flex-col ${msg.role === "user" ? "max-w-[min(70%,480px)]" : "max-w-[min(90%,720px)]"}`}>
                              <div className={msg.role === "user"
                                ? "bg-chat-user rounded-2xl px-4 py-2.5 text-[13px] leading-relaxed text-primary"
                                : "bg-chat-assistant rounded-2xl px-4 py-3 text-[13px] leading-relaxed text-primary"
                              }>
                                {msg.role === "user" ? (
                                  <p className="whitespace-pre-wrap">{msg.content}</p>
                                ) : (
                                  <div className="prose-chat">
                                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                                  </div>
                                )}
                              </div>
                              <span className={`text-[10px] mt-1 text-tertiary ${msg.role === "user" ? "text-right" : ""}`}>
                                {msg.created_at.includes("T") ? fmtTime(msg.created_at, tz) : msg.created_at}
                              </span>
                            </div>
                            {msg.role === "user" && (
                              <div className="w-7 h-7 bg-[#6B7280] rounded-full flex items-center justify-center text-white text-[10px] font-bold shrink-0 mt-0.5">
                                {userInitials}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
              {/* Streaming status — show steps and typing while waiting */}
              {isStreaming && (
                <div className="space-y-3">
                  {/* Research steps — shown inline during streaming even before text arrives */}
                  {researchSteps.length > 0 && !(messages[messages.length - 1]?.role === "assistant") && (
                    <div className="ml-10 space-y-1">
                      {researchSteps.map((step, i) => (
                        <div key={`${step.tool}-${i}`} className="flex items-start gap-2 text-[11px] text-secondary bg-surface-secondary rounded-md px-2.5 py-1.5">
                          {step.status === "running" ? (
                            <div className="w-3.5 h-3.5 border-[1.5px] border-apple-blue border-t-transparent rounded-full animate-spin shrink-0 mt-0.5" />
                          ) : (
                            <svg className="w-3.5 h-3.5 text-brand-green shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
                              <path d="M4.5 12.75l6 6 9-13.5" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          )}
                          <div>
                            <span>{step.description}</span>
                            {step.summary && <span className="text-tertiary ml-1">— {step.summary}</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Typing dots — show when no text has arrived yet */}
                  {(!messages[messages.length - 1] || messages[messages.length - 1]?.role === "user" || messages[messages.length - 1]?.content === "") && (
                    <div className="flex gap-2.5">
                      <div className="w-7 h-7 rounded-md flex items-center justify-center text-white text-[12px] font-bold shrink-0" style={{ background: "#6B8BA4" }}>R</div>
                      <div className="bg-chat-assistant rounded-2xl px-4 py-3">
                        <div className="flex items-center gap-1">
                          <span className="w-2 h-2 bg-tertiary rounded-full animate-bounce [animation-delay:0ms] [animation-duration:1s]" />
                          <span className="w-2 h-2 bg-tertiary rounded-full animate-bounce [animation-delay:150ms] [animation-duration:1s]" />
                          <span className="w-2 h-2 bg-tertiary rounded-full animate-bounce [animation-delay:300ms] [animation-duration:1s]" />
                        </div>
                        {researchSteps.length > 0 && (
                          <div className="text-[10px] text-tertiary mt-1.5">
                            {researchSteps.filter(s => s.status === "running")[0]?.description || "Analyzing..."}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input — matches main chat style */}
          <div className="shrink-0 px-5 pb-4 pt-2">
            <div className="flex items-end gap-2.5 bg-surface/95 backdrop-blur-sm border border-divider rounded-2xl px-4 py-3 shadow-md transition-all focus-within:border-apple-blue focus-within:shadow-lg">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={handleInput}
                onKeyDown={handleKeyDown}
                placeholder="Ask a tax research question..."
                rows={1}
                disabled={isStreaming}
                className="flex-1 resize-none bg-transparent text-[13px] text-primary outline-none min-h-[36px] max-h-[120px] leading-relaxed placeholder:text-tertiary disabled:opacity-50"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || isStreaming}
                className="shrink-0 w-8 h-8 rounded-xl bg-apple-blue text-white flex items-center justify-center hover:brightness-110 transition-all cursor-pointer text-[14px] disabled:opacity-30 shadow-sm"
                title="Send"
              >
                &#10148;
              </button>
            </div>
            {messages.length === 0 && !activeThreadId && (
              <div className="flex gap-1.5 mt-2 flex-wrap justify-center">
                {researchHints.map((hint) => (
                  <button
                    key={hint}
                    onClick={() => { setInput(hint); textareaRef.current?.focus(); }}
                    className="text-[10px] px-2.5 py-1 rounded-full border border-divider bg-surface text-secondary hover:border-apple-blue hover:text-apple-blue hover:bg-surface-secondary transition-all cursor-pointer"
                  >
                    {hint}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
}
