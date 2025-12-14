"use client";

import { usePathname } from "next/navigation";
import { SignedIn } from "@clerk/nextjs";
import { Navbar } from "./navbar";


export function ConditionalNavbar() {
  const pathname = usePathname();
  
  // Don't show navbar on chat page (has its own header)
  const isChatPage = pathname?.startsWith("/chat");
  if (isChatPage) {
    return null;
  }
  
  // Show navbar on dashboard and upload-file pages
  const isAuthPage = pathname?.startsWith("/dashboard") || 
                     pathname?.startsWith("/upload-file");
  
  if (isAuthPage) {
    return (
      <>
        <SignedIn>
          <Navbar />
        </SignedIn>
      </>
    );
  }
  
  // Show regular navbar on landing/public pages
  return <Navbar />;
}
