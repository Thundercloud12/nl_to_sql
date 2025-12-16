"use client";

import { usePathname } from "next/navigation";
import { SignedIn } from "@clerk/nextjs";
import { Navbar } from "./navbar";

export function ConditionalNavbar() {
  const pathname = usePathname();
  
  // Don't show navbar on chat page (typically has its own specific header or sidebar)
  const isChatPage = pathname?.startsWith("/chat");
  if (isChatPage) {
    return null;
  }
  
  // Logic: 
  // 1. If we are on public pages, show Navbar (Home, Pricing, etc).
  // 2. If we are on Dashboard/Upload, we usually want the navbar too 
  //    (unless you plan to switch to a Sidebar layout later).
  //    
  // The original code wrapped Dashboard/Upload in <SignedIn>, which is good practice.

  const isAuthPage = pathname?.startsWith("/dashboard") || 
                     pathname?.startsWith("/upload-file");
  
  if (isAuthPage) {
    return (
      <SignedIn>
        <Navbar />
      </SignedIn>
    );
  }
  
  // Default for Landing Page, Sign In, Sign Up, etc.
  return <Navbar />;
}