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

interface ChatPanelProps {
  clientName?: string;
  clientInitials?: string;
  clientColor?: string;
  workflowSteps?: string[];
  currentStep?: number;
  messages?: ChatMessage[];
  hints?: string[];
}

function ChatPanel({
  clientName = "Smith Family",
  clientInitials = "SM",
  clientColor = "#1D4ED8",
  workflowSteps = ["Intake", "Documents", "Review", "Prepare", "File"],
  currentStep = 2,
  messages = [],
  hints = ["Show W-2 summary", "Check missing docs", "Start 1040 prep"],
}: ChatPanelProps) {
  const [input, setInput] = useState("");

  return (
    <main className="flex-1 flex flex-col bg-white min-w-0">
      {/* Context bar */}
      <div className="h-12 shrink-0 border-b border-gray-100 flex items-center px-4 gap-3">
        <Avatar initials={clientInitials} color={clientColor} size="sm" />
        <span className="text-[13px] font-semibold text-[#1d1d1f]">{clientName}</span>

        {/* Workflow stepper */}
        <div className="flex items-center gap-1 ml-4">
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

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <div className="text-[40px] mb-2">&#128172;</div>
            <p className="text-[13px]">Start a conversation about this client&apos;s tax return.</p>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[70%] rounded-lg px-3 py-2 text-[13px] ${
                  msg.role === "user"
                    ? "bg-[#0071e3] text-white"
                    : "bg-[#f5f5f7] text-[#1d1d1f]"
                }`}
              >
                <p>{msg.content}</p>
                <div
                  className={`text-[10px] mt-1 ${
                    msg.role === "user" ? "text-white/60" : "text-gray-400"
                  }`}
                >
                  {msg.timestamp}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Input area */}
      <div className="shrink-0 border-t border-gray-100 p-3">
        <div className="flex items-end gap-2">
          <button className="shrink-0 w-8 h-8 rounded-lg border border-gray-200 flex items-center justify-center text-gray-400 hover:text-[#0071e3] hover:border-[#0071e3] transition-colors cursor-pointer text-[14px]">
            &#128206;
          </button>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about this client's tax return..."
            rows={1}
            className="flex-1 resize-none border border-gray-200 rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[#0071e3] transition-colors"
          />
          <button
            className="shrink-0 w-8 h-8 rounded-lg bg-[#0071e3] text-white flex items-center justify-center hover:brightness-110 transition-all cursor-pointer text-[14px] disabled:opacity-40"
            disabled={!input.trim()}
          >
            &#9652;
          </button>
        </div>

        {/* Quick hint chips */}
        <div className="flex gap-2 mt-2 flex-wrap">
          {hints.map((hint) => (
            <button
              key={hint}
              onClick={() => setInput(hint)}
              className="text-[11px] px-2.5 py-1 rounded-full border border-gray-200 text-gray-500 hover:border-[#0071e3] hover:text-[#0071e3] transition-colors cursor-pointer"
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
