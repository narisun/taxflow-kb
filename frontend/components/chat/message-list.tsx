"use client";

import { useEffect, useRef } from "react";
import { MessageBubble } from "./message-bubble";
import { TypingIndicator } from "./typing-indicator";

interface Message {
  id: number | string;
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  timestamp?: string;
}

interface MessageListProps {
  messages: Message[];
  isTyping?: boolean;
}

export function MessageList({ messages, isTyping = false }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4 pb-2 space-y-4">
      {messages.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-full text-gray-400">
          <div className="text-[40px] mb-2">&#128172;</div>
          <p className="text-[13px]">
            Start a conversation about this client&apos;s tax return.
          </p>
        </div>
      ) : (
        messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            role={msg.role}
            content={msg.content}
            timestamp={msg.timestamp || msg.created_at}
          />
        ))
      )}
      {isTyping && <TypingIndicator />}
      <div ref={bottomRef} />
    </div>
  );
}
