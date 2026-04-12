"use client";

import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { useState } from "react";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

interface TaxTracking {
  federal: number;       // positive = refund, negative = owed
  states: { code: string; amount: number }[];
}

interface ChatPanelProps {
  clientName?: string;
  clientInitials?: string;
  clientColor?: string;
  taxYear?: string;
  tracking?: TaxTracking;
  workflowSteps?: string[];
  currentStep?: number;
  messages?: ChatMessage[];
  hints?: string[];
}

function ChatPanel({
  clientName = "Smith Family",
  clientInitials = "SM",
  clientColor = "#1D4ED8",
  taxYear = "2025",
  tracking,
  workflowSteps = ["Intake", "Documents", "Review", "Prepare", "File"],
  currentStep = 2,
  messages = [],
  hints = ["Show W-2 summary", "Check missing docs", "Start 1040 prep"],
}: ChatPanelProps) {
  const [input, setInput] = useState("");

  const formatAmount = (amt: number) => {
    const sign = amt >= 0 ? "+" : "";
    return `${sign}$${Math.abs(amt).toLocaleString()}`;
  };

  const amountColor = (amt: number) =>
    amt >= 0 ? "text-green-600" : "text-red-500";

  return (
    <main className="flex-1 flex flex-col bg-white min-w-0">
      {/* Context bar */}
      <div className="shrink-0 border-b border-gray-100 px-5 py-3">
        {/* Top row: client + tracking labels */}
        <div className="flex items-center gap-3">
          <Avatar initials={clientInitials} color={clientColor} size="sm" />
          <div className="flex-1 min-w-0">
            <span className="text-[14px] font-semibold text-[#1d1d1f]">{clientName}</span>
          </div>

          {/* Federal / State tracking labels */}
          {tracking && (
            <div className="flex items-center gap-2">
              <span className={`text-[12px] font-semibold ${amountColor(tracking.federal)} bg-gray-50 px-2.5 py-1 rounded-md`}>
                Federal: {formatAmount(tracking.federal)}
              </span>
              {tracking.states.map((s) => (
                <span key={s.code} className={`text-[12px] font-semibold ${amountColor(s.amount)} bg-gray-50 px-2.5 py-1 rounded-md`}>
                  {s.code}: {formatAmount(s.amount)}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Second row: tax season + workflow stepper */}
        <div className="flex items-center gap-3 mt-2">
          <Badge variant="inProgress">{taxYear} Tax Season</Badge>

          <div className="w-px h-4 bg-gray-200" />

          {/* Workflow stepper */}
          <div className="flex items-center gap-1">
            {workflowSteps.map((step, i) => (
              <div key={step} className="flex items-center gap-1">
                {i > 0 && <div className="w-4 h-px bg-gray-300" />}
                <Badge
                  variant={
                    i < currentStep ? "completed" : i === currentStep ? "inProgress" : "pending"
                  }
                >
                  {step}
                </Badge>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <div className="text-[40px] mb-2">&#128172;</div>
            <p className="text-[13px]">Start a conversation about this client&apos;s tax return.</p>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-2.5 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              {msg.role === "assistant" && (
                <Avatar initials="TF" color="#1E3A5F" size="sm" className="mt-0.5 shrink-0" />
              )}
              <div className="flex flex-col max-w-[70%]">
                <div
                  className={`rounded-2xl px-4 py-3 text-[13px] leading-relaxed ${
                    msg.role === "user"
                      ? "text-[#1d1d1f]"
                      : "bg-[#f5f5f7] text-[#1d1d1f]"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                </div>
                <div
                  className={`text-[10px] mt-1 text-gray-400 ${
                    msg.role === "user" ? "text-right" : ""
                  }`}
                >
                  {msg.timestamp}
                </div>
              </div>
              {msg.role === "user" && (
                <Avatar initials="SC" color="#0d9488" size="sm" className="mt-0.5 shrink-0" />
              )}
            </div>
          ))
        )}
      </div>

      {/* Input area — elevated with more presence */}
      <div className="shrink-0 border-t border-gray-100 px-5 py-4 bg-[#fafafa]">
        <div className="flex items-end gap-2.5 bg-white border border-gray-200 rounded-2xl px-4 py-3 shadow-sm transition-all focus-within:border-[#0071e3] focus-within:shadow-md focus-within:bg-white hover:border-gray-300 hover:shadow-sm">
          <button className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-[#0071e3] hover:bg-blue-50 transition-colors cursor-pointer text-[15px]">
            &#128206;
          </button>
          <button className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-[#0071e3] hover:bg-blue-50 transition-colors cursor-pointer text-[15px]">
            &#9889;
          </button>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything about this return, or instruct the AI..."
            rows={2}
            className="flex-1 resize-none bg-transparent text-[14px] text-[#1d1d1f] outline-none min-h-[48px] max-h-[120px] leading-relaxed placeholder:text-gray-400"
          />
          <button
            className="shrink-0 w-9 h-9 rounded-xl bg-[#0071e3] text-white flex items-center justify-center hover:brightness-110 transition-all cursor-pointer text-[15px] disabled:opacity-30 shadow-sm"
            disabled={!input.trim()}
          >
            &#10148;
          </button>
        </div>

        {/* Quick hint chips */}
        <div className="flex gap-2 mt-2.5 flex-wrap">
          {hints.map((hint) => (
            <button
              key={hint}
              onClick={() => setInput(hint)}
              className="text-[11px] px-3 py-1.5 rounded-full border border-gray-200 bg-white text-gray-500 hover:border-[#0071e3] hover:text-[#0071e3] hover:bg-blue-50 transition-all cursor-pointer shadow-xs"
            >
              {hint}
            </button>
          ))}
        </div>
      </div>
    </main>
  );
}

export { ChatPanel, type ChatPanelProps, type ChatMessage };
