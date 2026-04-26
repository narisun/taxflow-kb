"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { MessageBubble } from "./message-bubble";
import { TypingIndicator } from "./typing-indicator";

interface Message {
  id: string | string;
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
  const [userScrolledUp, setUserScrolledUp] = useState(false);
  const lastMessageCount = useRef(0);

  useEffect(() => {
    const newCount = messages.length;
    const isInitialLoad = lastMessageCount.current === 0 && newCount > 0;
    const wasAdded = newCount > lastMessageCount.current && lastMessageCount.current > 0;
    lastMessageCount.current = newCount;

    if (isInitialLoad) {
      // Scroll instantly to bottom on first load (no animation)
      bottomRef.current?.scrollIntoView();
    } else if (wasAdded && !userScrolledUp) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages.length, userScrolledUp]);

  useEffect(() => {
    if (isTyping && !userScrolledUp) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [isTyping, userScrolledUp]);

  const firstMsgId = messages[0]?.id;
  useEffect(() => {
    lastMessageCount.current = 0;
    setUserScrolledUp(false);
  }, [firstMsgId]);

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setUserScrolledUp(distanceFromBottom > 100);
  }, []);

  return (
    <>
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="absolute inset-0 scroll-visible px-5 pb-36 flex flex-col"
      >
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center flex-1 text-tertiary">
            <svg className="w-10 h-10 mb-3 text-apple-blue/40" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1}>
              <path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <p className="text-[14px] font-medium text-secondary mb-1">
              TaxFlow AI Assistant
            </p>
            <p className="text-[12px] text-tertiary text-center max-w-[280px] leading-relaxed">
              Ask questions, check status, review documents, or use the quick actions below to get started.
            </p>
          </div>
        ) : (
          <>
            <div className="flex-1" />
            <div className="space-y-4 py-4">
              {messages.map((msg) => (
                <MessageBubble
                  key={msg.id}
                  role={msg.role}
                  content={msg.content}
                  timestamp={msg.timestamp || msg.created_at}
                />
              ))}
            </div>
          </>
        )}
        {isTyping && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {userScrolledUp && messages.length > 0 && (
        <button
          onClick={() => {
            setUserScrolledUp(false);
            bottomRef.current?.scrollIntoView({ behavior: "smooth" });
          }}
          className="absolute bottom-40 left-1/2 -translate-x-1/2 bg-surface text-primary text-[12px] px-3 py-1.5 rounded-full shadow-md border border-divider animate-fade-in cursor-pointer hover:bg-surface-secondary transition-colors z-10"
        >
          &darr; Latest messages
        </button>
      )}
    </>
  );
}
