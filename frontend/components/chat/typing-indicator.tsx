"use client";

export function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-chat-assistant rounded-xl px-4 py-3 flex items-center gap-1">
        <span className="w-2 h-2 bg-tertiary rounded-full animate-bounce [animation-delay:0ms] [animation-duration:1s]" />
        <span className="w-2 h-2 bg-tertiary rounded-full animate-bounce [animation-delay:150ms] [animation-duration:1s]" />
        <span className="w-2 h-2 bg-tertiary rounded-full animate-bounce [animation-delay:300ms] [animation-duration:1s]" />
      </div>
    </div>
  );
}
