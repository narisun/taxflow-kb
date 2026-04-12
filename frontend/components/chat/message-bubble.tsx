"use client";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
  userInitials?: string;
}

export function MessageBubble({ role, content, timestamp, userInitials = "SC" }: MessageBubbleProps) {
  const isUser = role === "user";

  return (
    <div className={`flex gap-2.5 ${isUser ? "justify-end" : "justify-start"}`}>
      {/* AI avatar — matches the TaxFlow AI logo style */}
      {!isUser && (
        <div className="w-7 h-7 bg-[#0071e3] rounded-md flex items-center justify-center text-white text-[12px] font-bold shrink-0 mt-0.5">
          T
        </div>
      )}
      <div className="flex flex-col max-w-[70%]">
        <div
          className={
            isUser
              ? "bg-[#e8edf2] rounded-2xl px-4 py-3 text-[13px] leading-relaxed text-[#1d1d1f]"
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
            className={`text-[10px] mt-1 text-gray-400 ${isUser ? "text-right" : ""}`}
          >
            {timestamp}
          </span>
        )}
      </div>
      {/* User avatar — rounded rectangle matching "T" logo shape */}
      {isUser && (
        <div className="w-7 h-7 bg-[#6B7280] rounded-md flex items-center justify-center text-white text-[10px] font-bold shrink-0 mt-0.5">
          {userInitials}
        </div>
      )}
    </div>
  );
}
