import type { Metadata } from "next";
import { Providers } from "./providers";
import { ConditionalNavbar } from "@/components/layout/conditional-navbar";
import "./globals.css";

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
    <html lang="en">
      <body className="min-h-screen">
        <Providers>
          <ConditionalNavbar />
          <main className="pt-16">
            {children}
          </main>
        </Providers>
      </body>
    </html>
  );
}
