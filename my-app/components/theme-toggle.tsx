"use client";

import * as React from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  // useEffect only runs on the client, so now we can safely show the UI
  React.useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <Button
        variant="ghost"
        size="sm"
        className="w-9 h-9 p-0 rounded-full hover:bg-white/5"
      >
        <span className="sr-only">Toggle theme</span>
        <div className="w-4 h-4" />
      </Button>
    );
  }

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      className="w-9 h-9 p-0 rounded-full hover:bg-white/5 transition-colors"
    >
      <Sun className={cn(
        "w-4 h-4 rotate-0 scale-100 transition-all",
        theme === "dark" ? "rotate-90 scale-0" : ""
      )} />
      <Moon className={cn(
        "absolute w-4 h-4 rotate-90 scale-0 transition-all",
        theme === "dark" ? "rotate-0 scale-100" : ""
      )} />
      <span className="sr-only">Toggle theme</span>
    </Button>
  );
}
