"use client";

import { Avatar } from "@/components/ui/avatar";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
}

export function MessageBubble({ role, content, timestamp }: MessageBubbleProps) {
  const isUser = role === "user";

  return (
    <div className={`flex gap-2 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <Avatar initials="TB" color="#1E3A5F" size="sm" className="mt-1" />
      )}
      <div className="flex flex-col max-w-[70%]">
        <div
          className={
            isUser
              ? "rounded-2xl px-4 py-3 text-[13px] leading-relaxed text-[#1d1d1f]"
              : "bg-[#f5f5f7] rounded-2xl px-4 py-3 text-[13px] leading-relaxed text-[#1d1d1f]"
          }
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{content}</p>
          ) : (
            <div
              className="whitespace-pre-wrap [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:pl-4 [&_ol]:list-decimal [&_ol]:pl-4"
              dangerouslySetInnerHTML={{ __html: content }}
            />
          )}
        </div>
        {timestamp && (
          <span
            className={`text-[10px] mt-1 ${
              isUser ? "text-gray-400 text-right" : "text-gray-400"
            }`}
          >
            {timestamp}
          </span>
        )}
      </div>
      {isUser && (
        <Avatar initials="SC" color="#0d9488" size="sm" className="mt-1" />
      )}
    </div>
  );
}
