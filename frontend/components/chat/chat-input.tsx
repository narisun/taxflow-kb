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
    <div className="shrink-0 border-t border-gray-100 p-3">
      <div className="flex items-end gap-2">
        <button
          onClick={onAttach}
          className="shrink-0 w-8 h-8 rounded-lg border border-gray-200 flex items-center justify-center text-gray-400 hover:text-[#0071e3] hover:border-[#0071e3] transition-colors cursor-pointer text-[14px]"
          title="Attach file"
        >
          &#128206;
        </button>
        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Ask about this client's tax return..."
          rows={1}
          disabled={disabled}
          className="flex-1 resize-none border border-gray-200 rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[#0071e3] transition-colors disabled:opacity-50"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || disabled}
          className="shrink-0 w-8 h-8 rounded-lg bg-[#0071e3] text-white flex items-center justify-center hover:brightness-110 transition-all cursor-pointer text-[14px] disabled:opacity-40"
          title="Send"
        >
          &#10148;
        </button>
      </div>

      {/* Quick hint chips */}
      <div className="flex gap-2 mt-2 flex-wrap">
        {hints.map((hint) => (
          <button
            key={hint}
            onClick={() => {
              setInput(hint);
              textareaRef.current?.focus();
            }}
            className="text-[11px] px-2.5 py-1 rounded-full border border-gray-200 text-gray-500 hover:border-[#0071e3] hover:text-[#0071e3] transition-colors cursor-pointer"
          >
            {hint}
          </button>
        ))}
      </div>
    </div>
  );
}
