import { cn } from "@/lib/utils";
import { type ButtonHTMLAttributes, forwardRef } from "react";

type ButtonVariant = "primary" | "secondary" | "pill" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-[#0071e3] text-white rounded-lg px-4 py-2 text-[17px] hover:brightness-110",
  secondary:
    "bg-[#1d1d1f] text-white rounded-lg px-4 py-2 text-[17px]",
  pill:
    "bg-transparent text-[#0066cc] border border-[#0066cc] rounded-[980px] px-4 py-2 text-[14px] hover:underline",
  ghost:
    "bg-transparent text-[#0066cc] text-[14px] hover:underline",
};

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", className, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "focus:outline-2 focus:outline-[#0071e3] focus:outline-offset-2 transition-all cursor-pointer",
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
