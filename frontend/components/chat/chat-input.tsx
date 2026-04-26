"use client";

import { useState, useRef, useCallback, KeyboardEvent } from "react";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  hints?: string[];
}

export function ChatInput({
  onSend,
  disabled = false,
  hints = ["Check status", "Review docs", "Run validations", "Compute return", "Analyze yoy", "Estimate refund", "Draft email", "Draft advisory", "Run pre-filing checks"],
}: ChatInputProps) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [input, onSend]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  };

  return (
    <div className="shrink-0 px-5 max-md:px-3 pb-4 pt-2">
      <div className="flex items-end gap-2.5 bg-surface/95 backdrop-blur-sm border border-divider rounded-2xl px-4 py-3 shadow-md transition-all focus-within:border-apple-blue focus-within:shadow-lg hover:shadow-md">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about this return..."
          rows={1}
          disabled={disabled}
          className="flex-1 resize-none bg-transparent text-[13px] text-primary outline-none min-h-[36px] max-h-[120px] leading-relaxed placeholder:text-tertiary disabled:opacity-50"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || disabled}
          className="shrink-0 w-8 h-8 rounded-xl bg-apple-blue text-white flex items-center justify-center hover:brightness-110 transition-all cursor-pointer text-[14px] disabled:opacity-30 shadow-sm"
          title="Send"
        >
          &#10148;
        </button>
      </div>

      <div className="hidden md:flex gap-1.5 mt-2 flex-wrap justify-center">
        {hints.map((hint) => (
          <button
            key={hint}
            onClick={() => onSend(hint)}
            disabled={disabled}
            className="text-[10px] px-2.5 py-1 rounded-full border border-divider bg-surface text-secondary hover:border-apple-blue hover:text-apple-blue hover:bg-surface-secondary transition-all cursor-pointer disabled:opacity-30"
          >
            {hint}
          </button>
        ))}
      </div>
    </div>
  );
}
