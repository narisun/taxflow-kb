import { cn } from "@/lib/utils";
import { type ButtonHTMLAttributes, forwardRef } from "react";

type ButtonVariant = "primary" | "secondary" | "pill" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-apple-blue text-white rounded-lg px-4 py-2 text-[17px] hover:brightness-110 active:scale-[0.98]",
  secondary:
    "bg-primary text-surface rounded-lg px-4 py-2 text-[17px] active:scale-[0.98]",
  pill:
    "bg-transparent text-apple-blue border border-apple-blue rounded-[980px] px-4 py-2 text-[14px] hover:underline active:scale-[0.98]",
  ghost:
    "bg-transparent text-apple-blue text-[14px] hover:underline",
};

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", className, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "focus-visible:outline-2 focus-visible:outline-apple-blue focus-visible:outline-offset-2 transition-all cursor-pointer",
          variantClasses[variant],
          className
        )}
        {...props}
      >
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";
export { Button, type ButtonProps, type ButtonVariant };
