"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";

interface ProductTourProps {
  active: boolean;
  onComplete: () => void;
}

const steps = [
  {
    title: "Meet your workspace",
    text: "Your clients are on the left. Chat with the AI tax agent in the center. Review documents and returns on the right.",
  },
  {
    title: "Start with a client",
    text: "Add a new client to begin. Upload their W-2s and 1099s, and the AI agent will help prepare their return.",
  },
  {
    title: "Ask anything",
    text: "Ask tax questions in plain English. The agent pulls from IRS rules, instructions, and publications to give you sourced answers.",
  },
];

export function ProductTour({ active, onComplete }: ProductTourProps) {
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (active) setStep(0);
  }, [active]);

  if (!active) return null;

  const current = steps[step];
  const isLast = step === steps.length - 1;

  return (
    <div className="fixed inset-0 z-[60] animate-fade-in">
      <div className="absolute inset-0 bg-black/60" />
      <div className="absolute inset-0 flex items-center justify-center p-4">
        <div className="bg-surface rounded-2xl p-6 shadow-xl max-w-[360px] w-full relative animate-scale-in">
          <div className="flex gap-1.5 mb-4 justify-center">
            {steps.map((_, i) => (
              <div
                key={i}
                className={cn(
                  "w-2 h-2 rounded-full transition-colors",
                  i <= step ? "bg-apple-blue" : "bg-surface-tertiary"
                )}
              />
            ))}
          </div>
          <h3 className="text-[17px] font-semibold text-primary mb-2">{current.title}</h3>
          <p className="text-[14px] text-secondary leading-relaxed mb-6">{current.text}</p>
          <div className="flex items-center justify-between">
            <button onClick={onComplete} className="text-[13px] text-tertiary hover:text-secondary cursor-pointer">
              Skip tour
            </button>
            <button
              onClick={() => { if (isLast) onComplete(); else setStep((s) => s + 1); }}
              className="px-4 py-2 rounded-lg bg-apple-blue text-white text-[14px] font-medium hover:brightness-110 transition-all cursor-pointer"
            >
              {isLast ? "Get Started" : "Next"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
