import * as React from "react";
import { cn } from "@/lib/utils";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "destructive";
  size?: "sm" | "md" | "lg";
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", ...props }, ref) => {
    const variants = {
      primary:
        "bg-primary text-primary-foreground hover:opacity-90 shadow-lg hover:shadow-xl transition-all duration-200",
      secondary:
        "bg-secondary text-secondary-foreground hover:opacity-90 transition-all duration-200",
      outline:
        "border-2 border-primary text-primary hover:bg-primary hover:text-primary-foreground transition-all duration-200",
      ghost:
        "text-foreground hover:bg-muted transition-all duration-200",
      destructive:
        "bg-error text-white hover:opacity-90 shadow-lg hover:shadow-xl transition-all duration-200",
    };

    const sizes = {
      sm: "px-3 py-1.5 text-sm rounded-md",
      md: "px-5 py-2.5 text-base rounded-lg",
      lg: "px-7 py-3.5 text-lg rounded-xl",
    };

    return (
      <button
        className={cn(
          "font-medium disabled:opacity-50 disabled:cursor-not-allowed active:scale-95 transition-transform inline-flex items-center justify-center",
          variants[variant],
          sizes[size],
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button };
