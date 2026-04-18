"use client";

import { useState, useRef, useCallback, useEffect, KeyboardEvent } from "react";
import { Modal } from "@/components/ui/modal";
import { cn } from "@/lib/utils";
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

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  } catch {
    return "";
  }
}

export function ResearchAgentModal({ open, onClose }: ResearchAgentModalProps) {
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

  // Load threads on mount / when modal opens
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
      .catch((err) => {
        if (!cancelled) setError(err.message || "Failed to load threads");
      })
      .finally(() => {
        if (!cancelled) setLoadingThreads(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Load messages when active thread changes
  useEffect(() => {
    if (!activeThreadId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    setLoadingMessages(true);
    setError(null);
    setResearchSteps([]);
    setStepsCollapsed(false);
    api.research
      .getMessages(activeThreadId)
      .then((res) => {
        if (cancelled) return;
        setMessages(
          res.messages.map((m) => ({
            id: m.id,
            role: m.role as "user" | "assistant",
            content: m.content,
            created_at: m.created_at,
          }))
        );
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "Failed to load messages");
      })
      .finally(() => {
        if (!cancelled) setLoadingMessages(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeThreadId]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isStreaming, researchSteps.length]);

  const handleSend = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || !activeThreadId || isStreaming) return;

    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setError(null);

    // Optimistic user message
    const userMsg: ResearchMessage = {
      id: `temp-${Date.now()}`,
      role: "user",
      content: trimmed,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsStreaming(true);
    setResearchSteps([]);
    setStepsCollapsed(false);

    const assistantMsgId = `stream-${Date.now()}`;
    let assistantAdded = false;

    try {
      const response = await api.research.sendMessage(activeThreadId, trimmed);
      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response stream");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        // Keep the last (possibly incomplete) line in buffer
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmedLine = line.trim();
          if (!trimmedLine.startsWith("data:")) continue;
          const jsonStr = trimmedLine.slice(5).trim();
          if (!jsonStr || jsonStr === "[DONE]") continue;

          try {
            const payload = JSON.parse(jsonStr);
            const eventType = payload.type;

            if (eventType === "step_start") {
              setResearchSteps((prev) => [
                ...prev,
                { tool: payload.tool, description: payload.description, status: "running" },
              ]);
            } else if (eventType === "step_complete") {
              setResearchSteps((prev) =>
                prev.map((s) =>
                  s.tool === payload.tool && s.status === "running"
                    ? { ...s, status: "complete", summary: payload.summary }
                    : s
                )
              );
            } else if (eventType === "text_delta") {
              if (!assistantAdded) {
                assistantAdded = true;
                setMessages((prev) => [
                  ...prev,
                  { id: assistantMsgId, role: "assistant", content: payload.text ?? "", created_at: new Date().toISOString() },
                ]);
              } else {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId
                      ? { ...m, content: m.content + (payload.text ?? "") }
                      : m
                  )
                );
              }
            } else if (eventType === "done") {
              // Auto-collapse steps when done
              setStepsCollapsed(true);
            } else if (eventType === "error") {
              setError(payload.message || "Stream error");
            }
          } catch {
            // Skip malformed JSON lines
          }
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to send message";
      setError(msg);
      // Remove the assistant placeholder if it was added but still empty
      if (assistantAdded) {
        setMessages((prev) => prev.filter((m) => m.id !== assistantMsgId || m.content.length > 0));
      }
    } finally {
      setIsStreaming(false);
    }
  }, [input, activeThreadId, isStreaming]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
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
      const msg = err instanceof Error ? err.message : "Failed to create thread";
      setError(msg);
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
      const msg = err instanceof Error ? err.message : "Failed to delete thread";
      setError(msg);
    }
  };

  return (
    <Modal open={open} onClose={onClose} className="max-w-6xl w-[92vw]">
      <div className="flex h-[75vh] max-h-[700px]">
        {/* Left: Thread list */}
        <div className="w-64 shrink-0 border-r border-divider flex flex-col bg-bg">
          {/* Header */}
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

          {/* Thread list */}
          <div className="flex-1 overflow-y-auto scroll-visible">
            {loadingThreads && (
              <div className="flex items-center justify-center py-8">
                <div className="w-5 h-5 border-2 border-apple-blue border-t-transparent rounded-full animate-spin" />
              </div>
            )}
            {!loadingThreads && threads.length === 0 && (
              <div className="px-4 py-8 text-center text-[11px] text-tertiary">
                No threads yet. Start a new research conversation.
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
                      {formatTime(thread.updated_at || thread.created_at)}
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteThread(thread.id);
                      }}
                      className="hidden group-hover:block text-[10px] text-tertiary hover:text-red-500 cursor-pointer"
                      title="Delete thread"
                    >
                      &times;
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Chat */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Chat header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-divider shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <span className="w-6 h-6 rounded-md flex items-center justify-center text-white text-[10px] font-bold shrink-0" style={{ background: "#6B8BA4" }}>R</span>
              <span className="text-[13px] font-semibold text-primary truncate" title={threads.find((t) => t.id === activeThreadId)?.title || "Research Agent"}>
                {threads.find((t) => t.id === activeThreadId)?.title || "Research Agent"}
              </span>
            </div>
            <button onClick={onClose} className="text-[13px] text-secondary hover:text-primary cursor-pointer">&times;</button>
          </div>

          {/* Error banner */}
          {error && (
            <div className="px-4 py-2 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-[12px] border-b border-divider flex items-center justify-between">
              <span>{error}</span>
              <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600 cursor-pointer">&times;</button>
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto scroll-visible px-4 py-4 space-y-4">
            {loadingMessages && (
              <div className="flex items-center justify-center py-8">
                <div className="w-5 h-5 border-2 border-apple-blue border-t-transparent rounded-full animate-spin" />
              </div>
            )}
            {!loadingMessages && !activeThreadId && (
              <div className="flex items-center justify-center py-8 text-[12px] text-tertiary">
                Select or create a thread to start researching.
              </div>
            )}
            {!loadingMessages &&
              messages.map((msg, idx) => {
                // Show research steps panel above the last assistant message that is streaming
                const isLastAssistant =
                  msg.role === "assistant" && idx === messages.length - 1 && researchSteps.length > 0;

                return (
                  <div key={msg.id}>
                    {/* Research steps panel */}
                    {isLastAssistant && (
                      <div className="mb-3 ml-8">
                        <button
                          onClick={() => setStepsCollapsed((prev) => !prev)}
                          className="flex items-center gap-1.5 text-[11px] font-medium text-secondary mb-1.5 cursor-pointer hover:text-primary transition-colors"
                        >
                          <svg
                            className={cn("w-3 h-3 transition-transform", stepsCollapsed ? "" : "rotate-90")}
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                            strokeWidth={2}
                          >
                            <path d="M9 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                          Research steps ({researchSteps.length})
                        </button>
                        {!stepsCollapsed && (
                          <div className="space-y-1 pl-1">
                            {researchSteps.map((step, i) => (
                              <div
                                key={`${step.tool}-${i}`}
                                className="flex items-start gap-2 text-[11px] text-secondary bg-surface-secondary rounded-md px-2.5 py-1.5"
                              >
                                {step.status === "running" ? (
                                  <div className="w-3.5 h-3.5 border-[1.5px] border-apple-blue border-t-transparent rounded-full animate-spin shrink-0 mt-0.5" />
                                ) : (
                                  <svg className="w-3.5 h-3.5 text-green-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
                                    <path d="M4.5 12.75l6 6 9-13.5" strokeLinecap="round" strokeLinejoin="round" />
                                  </svg>
                                )}
                                <div>
                                  <span>{step.description}</span>
                                  {step.summary && (
                                    <span className="text-tertiary ml-1">-- {step.summary}</span>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Message bubble */}
                    <div className={`flex gap-2.5 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                      {msg.role === "assistant" && (
                        <span className="w-6 h-6 rounded-md flex items-center justify-center text-white text-[10px] font-bold shrink-0 mt-0.5" style={{ background: "#6B8BA4" }}>R</span>
                      )}
                      <div className={cn(
                        "max-w-[75%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed",
                        msg.role === "user"
                          ? "bg-chat-user text-primary"
                          : "bg-chat-assistant text-primary"
                      )}>
                        {msg.role === "user" ? (
                          <p className="whitespace-pre-wrap">{msg.content}</p>
                        ) : (
                          <div className="prose prose-sm max-w-none dark:prose-invert [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0.5">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {msg.content}
                            </ReactMarkdown>
                          </div>
                        )}
                        <div className="text-[10px] text-tertiary mt-1">{formatTime(msg.created_at)}</div>
                      </div>
                      {msg.role === "user" && (
                        <span className="w-6 h-6 bg-[#6B7280] rounded-md flex items-center justify-center text-white text-[10px] font-bold shrink-0 mt-0.5">SC</span>
                      )}
                    </div>
                  </div>
                );
              })}
            {isStreaming && messages[messages.length - 1]?.content === "" && (
              <div className="flex gap-2.5">
                <span className="w-6 h-6 rounded-md flex items-center justify-center text-white text-[10px] font-bold shrink-0" style={{ background: "#6B8BA4" }}>R</span>
                <div className="bg-chat-assistant rounded-xl px-4 py-3 flex items-center gap-1">
                  <span className="w-2 h-2 bg-tertiary rounded-full animate-bounce [animation-delay:0ms] [animation-duration:1s]" />
                  <span className="w-2 h-2 bg-tertiary rounded-full animate-bounce [animation-delay:150ms] [animation-duration:1s]" />
                  <span className="w-2 h-2 bg-tertiary rounded-full animate-bounce [animation-delay:300ms] [animation-duration:1s]" />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="shrink-0 px-4 pb-4 pt-2 border-t border-divider">
            <div className="flex items-end gap-2 bg-surface border border-divider rounded-xl px-3 py-2 focus-within:border-apple-blue transition-colors">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={handleInput}
                onKeyDown={handleKeyDown}
                placeholder="Ask a tax research question..."
                rows={1}
                disabled={!activeThreadId || isStreaming}
                className="flex-1 resize-none bg-transparent text-[13px] text-primary outline-none min-h-[36px] max-h-[120px] leading-relaxed placeholder:text-tertiary disabled:opacity-50"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || !activeThreadId || isStreaming}
                className="shrink-0 w-8 h-8 rounded-lg bg-apple-blue text-white flex items-center justify-center hover:brightness-110 transition-all cursor-pointer text-[14px] disabled:opacity-30"
              >
                &#10148;
              </button>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  );
}
