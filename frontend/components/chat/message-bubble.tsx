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
    <div className={`flex gap-2.5 animate-message-in ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-md flex items-center justify-center text-white text-[12px] font-bold shrink-0 mt-0.5" style={{ background: "#3a3d42" }}>
          T
        </div>
      )}
      <div className="flex flex-col max-w-[min(70%,560px)] max-md:max-w-[85%]">
        <div
          className={
            isUser
              ? "bg-chat-user rounded-2xl px-4 py-3 text-[13px] leading-relaxed text-primary"
              : "bg-chat-assistant rounded-2xl px-4 py-3 text-[13px] leading-relaxed text-primary"
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
