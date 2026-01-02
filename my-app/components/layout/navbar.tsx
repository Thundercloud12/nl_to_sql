"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SignedIn, SignedOut, UserButton } from "@clerk/nextjs";
import { motion } from "framer-motion";
import { 
  Database, 
  MessageSquare, 
  Home, 
  Command, 
  Terminal,
  BarChart3
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";

export function Navbar() {
  const pathname = usePathname();

  const navItems = [
    { href: "/", label: "Home", icon: Home },
    { href: "/dashboard", label: "Dashboard", icon: Database },
    { href: "/chat", label: "Chat", icon: MessageSquare },
  ];

  return (
    <motion.nav
      initial={{ y: -100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="fixed top-0 left-0 right-0 z-50 border-b border-black/5 dark:border-white/5 bg-white/80 dark:bg-[#0D0E12]/80 backdrop-blur-md"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          
          {/* Logo Section */}
          <Link href="/" className="flex items-center space-x-2 group">
            <div className="w-8 h-8 bg-black dark:bg-[#00e599] rounded-lg flex items-center justify-center text-white dark:text-black shadow-sm dark:shadow-[0_0_15px_-3px_#00e599]">
                <Command size={18} />
            </div>
            <span className="text-lg font-bold tracking-tighter text-foreground dark:text-white group-hover:text-primary dark:group-hover:text-[#00e599] transition-colors">
              RELIX
            </span>
          </Link>

          {/* Navigation Links - Centered & Modern */}
          <div className="hidden md:flex items-center space-x-1">
            <SignedIn>
              <div className="flex items-center gap-1 bg-black/5 dark:bg-white/5 rounded-full p-1 border border-black/5 dark:border-white/5">
                {navItems.map((item) => {
                  const Icon = item.icon;
                  const isActive = pathname === item.href;
                  
                  return (
                    <Link key={item.href} href={item.href} className="relative">
                      {isActive && (
                        <motion.div
                          layoutId="navbar-active"
                          className="absolute inset-0 bg-white dark:bg-[#00e599]/10 rounded-full border border-black/5 dark:border-[#00e599]/20 shadow-sm dark:shadow-none"
                          transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                        />
                      )}
                      <span
                        className={cn(
                          "relative flex items-center space-x-2 px-4 py-2 rounded-full text-sm font-medium transition-colors duration-200",
                          isActive 
                            ? "text-black dark:text-[#00e599]" 
                            : "text-zinc-600 dark:text-zinc-400 hover:text-black dark:hover:text-white"
                        )}
                      >
                        <Icon className="w-4 h-4" />
                        <span>{item.label}</span>
                      </span>
                    </Link>
                  );
                })}
              </div>
            </SignedIn>
          </div>

          {/* Right Section: Auth */}
          <div className="flex items-center space-x-4">
            <SignedOut>
              <Link href="/sign-in">
                <Button variant="ghost" size="sm" className="text-zinc-600 dark:text-zinc-400 hover:text-black dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5">
                  Sign In
                </Button>
              </Link>
              <Link href="/sign-up">
                <Button size="sm" className="bg-black dark:bg-[#00e599] text-white dark:text-black hover:bg-black/90 dark:hover:bg-[#00e599]/90 font-semibold rounded-full px-6 shadow-sm">
                  Sign Up
                </Button>
              </Link>
            </SignedOut>
            
            <SignedIn>
              {/* Customizing Clerk Trigger to match Dark Theme */}
              <div className="flex items-center gap-4">
                <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-md bg-zinc-100 dark:bg-[#1A1C23] border border-zinc-200 dark:border-white/10">
                    <div className="w-2 h-2 rounded-full bg-green-500 dark:bg-[#00e599] animate-pulse" />
                    <span className="text-xs text-zinc-600 dark:text-zinc-400 font-mono">System Operational</span>
                </div>
                <ThemeToggle />
                <UserButton
                  afterSignOutUrl="/"
                  appearance={{
                    elements: {
                      avatarBox: "w-9 h-9 border-2 border-black/10 dark:border-[#00e599]/20",
                      userButtonPopoverCard: "bg-white dark:bg-[#0D0E12] border border-black/10 dark:border-white/10 shadow-2xl",
                      userButtonPopoverFooter: "hidden",
                      userButtonPopoverActionButtonText: "text-foreground dark:text-white hover:text-primary dark:hover:text-[#00e599]",
                      userButtonPopoverActionButtonIcon: "text-zinc-500 dark:text-zinc-400",
                    },
                  }}
                />
              </div>
            </SignedIn>
          </div>
        </div>
      </div>
    </motion.nav>
  );
}