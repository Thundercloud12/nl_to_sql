import type { Metadata } from "next";
import { ConditionalNavbar } from "@/components/layout/conditional-navbar";
import "./globals.css";
import { ClerkProvider } from "@clerk/nextjs";

export const metadata: Metadata = {
  title: "RELIX AI - Natural Language to SQL",
  description: "Transform your questions into powerful data insights using AI",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider>
    <html lang="en">
      <body className="min-h-screen">
          <ConditionalNavbar />
          <main className="pt-16">
            {children}
          </main>

      </body>
    </html>
  </ClerkProvider>
  );
}
