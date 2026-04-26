import { cn } from "@/lib/utils";
import { type InputHTMLAttributes, forwardRef } from "react";

type InputValidation = "default" | "ok" | "warning" | "error";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  validation?: InputValidation;
}

const validationClasses: Record<InputValidation, string> = {
  default: "border-divider focus:border-apple-blue",
  ok: "border-brand-green bg-brand-green/10",
  warning: "border-orange-500 bg-orange-50 dark:bg-orange-950/30",
  error: "border-red-500 bg-red-50 dark:bg-red-950/30",
};

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ validation = "default", className, ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={cn(
          "border-[1.5px] rounded-lg px-3 py-2 text-[13px] outline-none transition-colors w-full bg-surface text-primary placeholder:text-tertiary",
          validationClasses[validation],
          className
        )}
        {...props}
      />
    );
  }
);

Input.displayName = "Input";
export { Input, type InputProps, type InputValidation };
