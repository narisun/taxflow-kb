"use client";

import { useState, useRef, useCallback, KeyboardEvent } from "react";

interface ChatInputProps {
  onSend: (message: string) => void;
  onAttach?: () => void;
  disabled?: boolean;
  hints?: string[];
}

export function ChatInput({
  onSend,
  onAttach,
  disabled = false,
  hints = ["Refund estimate", "Missing docs", "Year-over-year", "Credits check"],
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
    <div className="shrink-0 px-5 pb-4 pt-2">
      <div className="flex items-end gap-2.5 bg-white/95 backdrop-blur-sm border border-gray-200 rounded-2xl px-4 py-3 shadow-md transition-all focus-within:border-[#0071e3] focus-within:shadow-lg hover:border-gray-300 hover:shadow-md">
        <button
          onClick={onAttach}
          className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-[#0071e3] hover:bg-blue-50 transition-colors cursor-pointer text-[15px]"
          title="Attach file"
        >
          &#128206;
        </button>
        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about this return, or instruct the AI..."
          rows={2}
          disabled={disabled}
          className="flex-1 resize-none bg-transparent text-[14px] text-[#1d1d1f] outline-none min-h-[48px] max-h-[120px] leading-relaxed placeholder:text-gray-400 disabled:opacity-50"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || disabled}
          className="shrink-0 w-9 h-9 rounded-xl bg-[#0071e3] text-white flex items-center justify-center hover:brightness-110 transition-all cursor-pointer text-[15px] disabled:opacity-30 shadow-sm"
          title="Send"
        >
          &#10148;
        </button>
      </div>

      {/* Quick hint / action chips */}
      <div className="flex gap-2 mt-2 flex-wrap">
        {hints.map((hint) => (
          <button
            key={hint}
            onClick={() => {
              setInput(hint);
              textareaRef.current?.focus();
            }}
            className="text-[11px] px-3 py-1 rounded-full border border-gray-200 bg-white text-gray-500 hover:border-[#0071e3] hover:text-[#0071e3] hover:bg-blue-50/50 transition-all cursor-pointer"
          >
            {hint}
          </button>
        ))}
      </div>
    </div>
  );
}
