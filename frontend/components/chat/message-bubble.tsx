"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
  userInitials?: string;
}

export function MessageBubble({ role, content, timestamp, userInitials = "SC" }: MessageBubbleProps) {
  const isUser = role === "user";

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
        {timestamp && (
          <span className={`text-[10px] mt-1 text-tertiary ${isUser ? "text-right" : ""}`}>
            {timestamp}
          </span>
        )}
      </div>
      {isUser && (
        <div className="w-7 h-7 bg-[#6B7280] rounded-md flex items-center justify-center text-white text-[10px] font-bold shrink-0 mt-0.5">
          {userInitials}
        </div>
      )}
    </div>
  );
}
