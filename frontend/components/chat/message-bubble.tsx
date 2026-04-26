"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { fmtTime, deriveInitials } from "@/lib/utils";
import { useTimezone, useMeOrNull } from "@/components/auth/me-context";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
  userInitials?: string;
}

export function MessageBubble({ role, content, timestamp, userInitials }: MessageBubbleProps) {
  const isUser = role === "user";
  const tz = useTimezone();
  const me = useMeOrNull();

  const initials = userInitials || deriveInitials(me?.user?.name, me?.user?.email);

  const displayTime = timestamp
    ? timestamp.includes("T") || timestamp.includes("Z") ? fmtTime(timestamp, tz) : timestamp
    : undefined;

  return (
    <div className={`flex gap-2.5 animate-message-in ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-md flex items-center justify-center text-white text-[12px] font-bold shrink-0 mt-0.5" style={{ background: "#6B8BA4" }}>
          T
        </div>
      )}
      <div className={`flex flex-col ${isUser ? "max-w-[min(70%,480px)]" : "max-w-[min(90%,720px)]"} max-md:max-w-[90%]`}>
        <div
          className={
            isUser
              ? "bg-chat-user rounded-2xl px-4 py-2.5 text-[13px] leading-relaxed text-primary"
              : "bg-chat-assistant rounded-2xl px-4 py-3 text-[13px] leading-relaxed text-primary"
          }
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{content}</p>
          ) : (
            <div className="prose-chat">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
            </div>
          )}
        </div>
        {displayTime && (
          <span className={`text-[10px] mt-1 text-tertiary ${isUser ? "text-right" : ""}`}>
            {displayTime}
          </span>
        )}
      </div>
      {isUser && (
        <div className="w-7 h-7 bg-[#6B7280] rounded-full flex items-center justify-center text-white text-[10px] font-bold shrink-0 mt-0.5">
          {initials}
        </div>
      )}
    </div>
  );
}
