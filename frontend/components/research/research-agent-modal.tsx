"use client";

import { useState, useRef, useCallback, useEffect, KeyboardEvent } from "react";
import { Modal } from "@/components/ui/modal";
import { cn } from "@/lib/utils";

interface ResearchAgentModalProps {
  open: boolean;
  onClose: () => void;
}

interface ResearchMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

interface ResearchThread {
  id: number;
  title: string;
  lastMessage: string;
  date: string;
  messages: ResearchMessage[];
}

const now = () => new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });

const mockThreads: ResearchThread[] = [
  {
    id: 1,
    title: "SALT deduction cap for 2025",
    lastMessage: "The $10,000 SALT cap remains in effect for TY 2025...",
    date: "Today",
    messages: [
      { id: 1, role: "user", content: "What is the current SALT deduction cap for 2025 and is there any legislation to change it?", timestamp: "10:15 AM" },
      { id: 2, role: "assistant", content: "The <strong>$10,000 SALT (State and Local Tax) deduction cap</strong> remains in effect for TY 2025. This cap was established by the Tax Cuts and Jobs Act (TCJA) of 2017 and applies to the combined total of:\n\n\u2022 State and local income taxes (or sales taxes)\n\u2022 Property taxes\n\nThe cap is $10,000 for both single and married filing jointly, which creates a marriage penalty.\n\n<strong>Pending legislation:</strong> The SALT Caucus has proposed raising the cap to $80,000 as part of broader tax reform discussions, but no bill has passed as of April 2026. The original TCJA cap is set to expire after TY 2025 unless extended.\n\n<strong>Planning note:</strong> For clients in high-tax states (NY, NJ, CA, CT), this cap significantly limits itemized deductions. Consider whether bunching property tax payments or timing state estimated payments can optimize across tax years.", timestamp: "10:15 AM" },
    ],
  },
  {
    id: 2,
    title: "Qualified business income deduction",
    lastMessage: "Section 199A provides a 20% deduction for QBI...",
    date: "Yesterday",
    messages: [
      { id: 3, role: "user", content: "Can you explain the QBI deduction rules for a client with both W-2 income and Schedule C income?", timestamp: "3:30 PM" },
      { id: 4, role: "assistant", content: "The <strong>Section 199A Qualified Business Income (QBI) deduction</strong> allows eligible taxpayers to deduct up to <strong>20% of qualified business income</strong> from pass-through entities.\n\n<strong>For a client with W-2 + Schedule C:</strong>\n\n1. The W-2 income is <strong>not</strong> eligible for QBI \u2014 only the Schedule C net profit qualifies\n2. The deduction is the <strong>lesser of:</strong>\n   \u2022 20% of QBI, or\n   \u2022 20% of taxable income (before QBI deduction) minus net capital gains\n\n<strong>Income phase-outs (2025):</strong>\n\u2022 Single: begins at $191,950, fully phased out at $241,950\n\u2022 MFJ: begins at $383,900, fully phased out at $483,900\n\nAbove the threshold, additional limitations apply based on W-2 wages paid and property held by the business.\n\n<strong>Specified service trades (SSTBs):</strong> If the Schedule C is for health, law, consulting, athletics, or financial services, the deduction is further limited and fully eliminated above the phase-out range.", timestamp: "3:30 PM" },
      { id: 5, role: "user", content: "What about a client who is an attorney with $180K Schedule C income filing single?", timestamp: "3:35 PM" },
      { id: 6, role: "assistant", content: "For a <strong>single attorney with $180K Schedule C income</strong>:\n\nLegal services is a <strong>Specified Service Trade or Business (SSTB)</strong>, so special rules apply.\n\nSince the taxable income is <strong>below $191,950</strong> (the phase-out threshold for single filers), the SSTB limitation does <strong>not</strong> apply. The client can claim the full 20% QBI deduction.\n\n<strong>Calculation:</strong>\n\u2022 QBI = $180,000 (Schedule C net profit)\n\u2022 20% of QBI = <strong>$36,000</strong>\n\u2022 Compare to 20% of taxable income (after standard deduction)\n\u2022 Taxable income \u2248 $180,000 - $15,000 = $165,000\n\u2022 20% of $165,000 = $33,000\n\n<strong>QBI deduction = $33,000</strong> (the lesser amount)\n\nThis saves approximately <strong>$7,920</strong> in federal tax (at the 24% bracket).\n\n\u26A0 <strong>Important:</strong> If this client\u2019s total income exceeds $191,950 (e.g., with investment income), the SSTB phase-out begins and the deduction reduces proportionally.", timestamp: "3:35 PM" },
    ],
  },
  {
    id: 3,
    title: "EV tax credit eligibility",
    lastMessage: "The clean vehicle credit under IRC 30D...",
    date: "Apr 9",
    messages: [
      { id: 7, role: "user", content: "Client bought a Tesla Model Y in 2025. Do they qualify for the EV tax credit?", timestamp: "11:00 AM" },
      { id: 8, role: "assistant", content: "For a <strong>Tesla Model Y purchased in 2025</strong>, eligibility for the <strong>Clean Vehicle Credit (IRC \u00a730D)</strong> depends on several factors:\n\n<strong>Vehicle requirements (all must be met):</strong>\n\u2713 Final assembly in North America \u2014 Tesla Model Y qualifies\n\u2713 MSRP cap: $80,000 for SUVs/trucks \u2014 Model Y qualifies (base ~$45K)\n\u2713 Battery component & critical mineral sourcing requirements\n\n<strong>Buyer requirements:</strong>\n\u2022 Modified AGI must be below:\n  \u2013 $300,000 MFJ\n  \u2013 $225,000 HOH\n  \u2013 $150,000 Single/other\n\u2022 Cannot have claimed the credit in the prior 3 years\n\n<strong>Credit amount:</strong>\n\u2022 Up to <strong>$7,500</strong> ($3,750 for battery components + $3,750 for critical minerals)\n\u2022 Tesla has historically met both requirements, but verify at fueleconomy.gov for the specific VIN\n\n<strong>Transfer option:</strong> Starting 2024, buyers can transfer the credit to the dealer at point of sale for an immediate price reduction.\n\nI recommend checking the VIN against the IRS qualified vehicle list.", timestamp: "11:00 AM" },
    ],
  },
];

export function ResearchAgentModal({ open, onClose }: ResearchAgentModalProps) {
  const [threads, setThreads] = useState<ResearchThread[]>(mockThreads);
  const [activeThreadId, setActiveThreadId] = useState<number | null>(mockThreads[0]?.id ?? null);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const activeThread = threads.find((t) => t.id === activeThreadId);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeThread?.messages.length, isTyping]);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || !activeThreadId) return;

    const userMsg: ResearchMessage = { id: Date.now(), role: "user", content: trimmed, timestamp: now() };

    setThreads((prev) => prev.map((t) =>
      t.id === activeThreadId
        ? { ...t, messages: [...t.messages, userMsg], lastMessage: trimmed, date: "Now" }
        : t
    ));
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setIsTyping(true);

    setTimeout(() => {
      const aiMsg: ResearchMessage = {
        id: Date.now() + 1,
        role: "assistant",
        content: `Based on my research of IRS publications and tax code, here is what I found regarding your question about \u201c${trimmed.slice(0, 60)}${trimmed.length > 60 ? "\u2026" : ""}\u201d:\n\nThis is a complex area that depends on several factors. I recommend reviewing <strong>IRS Publication 17</strong> for general guidance, and the specific code section for detailed rules.\n\nWould you like me to dig deeper into any particular aspect?`,
        timestamp: now(),
      };
      setThreads((prev) => prev.map((t) =>
        t.id === activeThreadId
          ? { ...t, messages: [...t.messages, aiMsg], lastMessage: aiMsg.content.slice(0, 60) }
          : t
      ));
      setIsTyping(false);
    }, 1500);
  }, [input, activeThreadId]);

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

  const handleNewThread = () => {
    const id = Date.now();
    const thread: ResearchThread = {
      id,
      title: "New research",
      lastMessage: "Start a new research conversation",
      date: "Now",
      messages: [
        { id: id + 1, role: "assistant", content: "How can I help with your tax research today? I can look up IRS rules, analyze tax scenarios, compare filing strategies, or explain specific code sections.", timestamp: now() },
      ],
    };
    setThreads((prev) => [thread, ...prev]);
    setActiveThreadId(id);
  };

  return (
    <Modal open={open} onClose={onClose} className="max-w-5xl">
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
            {threads.map((thread) => (
              <div
                key={thread.id}
                onClick={() => setActiveThreadId(thread.id)}
                className={cn(
                  "px-4 py-3 border-b border-divider cursor-pointer transition-colors",
                  activeThreadId === thread.id ? "bg-apple-blue/10" : "hover:bg-surface-secondary"
                )}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <span className={cn(
                    "text-[12px] truncate",
                    activeThreadId === thread.id ? "font-semibold text-apple-blue" : "font-medium text-primary"
                  )}>
                    {thread.title}
                  </span>
                  <span className="text-[10px] text-tertiary shrink-0 ml-2">{thread.date}</span>
                </div>
                <div className="text-[10px] text-tertiary truncate">{thread.lastMessage}</div>
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
              <span className="text-[13px] font-semibold text-primary truncate">
                {activeThread?.title || "Research Agent"}
              </span>
            </div>
            <button onClick={onClose} className="text-[13px] text-secondary hover:text-primary cursor-pointer">&times;</button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto scroll-visible px-4 py-4 space-y-4">
            {activeThread?.messages.map((msg) => (
              <div key={msg.id} className={`flex gap-2.5 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
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
                    <div className="whitespace-pre-wrap [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:pl-4" dangerouslySetInnerHTML={{ __html: msg.content }} />
                  )}
                  <div className="text-[10px] text-tertiary mt-1">{msg.timestamp}</div>
                </div>
                {msg.role === "user" && (
                  <span className="w-6 h-6 bg-[#6B7280] rounded-md flex items-center justify-center text-white text-[10px] font-bold shrink-0 mt-0.5">SC</span>
                )}
              </div>
            ))}
            {isTyping && (
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
                className="flex-1 resize-none bg-transparent text-[13px] text-primary outline-none min-h-[36px] max-h-[120px] leading-relaxed placeholder:text-tertiary"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim()}
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
