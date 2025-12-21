// app/providers.tsx
"use client";

import { useEffect, useState } from "react";
import { ClerkProvider } from "@clerk/nextjs";

export function Providers({ children }: { children: React.ReactNode }) {
  const [backendReady, setBackendReady] = useState(false);

  useEffect(() => {
    const wakeupServer = async () => {
      let retries = 0;
      const maxRetries = 10;
      const initialDelay = 1000; // 1 second

      const attemptConnection = async () => {
        try {
          const response = await fetch("http://localhost:8000/health", {
            method: "GET",
            signal: AbortSignal.timeout(5000)
          });

          if (!response.ok) {
            throw new Error(`Health check returned ${response.status}`);
          }

          const data = await response.json();
          console.log("✅ Backend server is awake:", data);
          setBackendReady(true);
          return true;
        } catch (error) {
          retries++;
          if (retries < maxRetries) {
            const delayMs = initialDelay * Math.pow(2, retries - 1);
            console.warn(
              `⏳ Backend not ready (attempt ${retries}/${maxRetries}). Retrying in ${delayMs}ms...`,
              error
            );
            await new Promise(resolve => setTimeout(resolve, delayMs));
            return attemptConnection();
          } else {
            console.error("❌ Backend failed to respond after 10 retries. Proceeding anyway.");
            setBackendReady(true); // Fallback: proceed anyway
            return false;
          }
        }
      };

      await attemptConnection();
    };

    wakeupServer();
  }, []);

  if (!backendReady) {
    return (
      <div className="fixed inset-0 flex flex-col items-center justify-center bg-white z-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
          <p className="text-lg text-gray-600 font-semibold">Warming up backend...</p>
          <p className="text-sm text-gray-400 mt-2">This may take a moment on first load</p>
        </div>
      </div>
    );
  }

  return (
    <ClerkProvider>
      {children}
    </ClerkProvider>
  );
}