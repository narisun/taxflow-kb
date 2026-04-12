"use client";

import { useEffect, useRef, useState, useCallback } from "react";
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
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    if (autoScroll) scrollToBottom();
  }, [messages, isTyping, autoScroll, scrollToBottom]);

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setAutoScroll(distanceFromBottom < 100);
  }, []);

  return (
    <div className="relative flex-1 overflow-hidden">
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="h-full overflow-y-auto px-5 py-4 pb-2 space-y-4"
      >
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-tertiary">
            <svg className="w-10 h-10 mb-3 text-tertiary" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1}>
              <path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
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

      {!autoScroll && (
        <button
          onClick={() => { setAutoScroll(true); scrollToBottom(); }}
          className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-surface text-primary text-[12px] px-3 py-1.5 rounded-full shadow-md border border-divider animate-fade-in cursor-pointer hover:bg-surface-secondary transition-colors"
        >
          &darr; New messages
        </button>
      )}
    </div>
  );
}
