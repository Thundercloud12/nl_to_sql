import { useState, useEffect } from "react";

export function useServerHealth() {
  const [isHealthy, setIsHealthy] = useState(false);
  const [isChecking, setIsChecking] = useState(true);

  useEffect(() => {
    const checkHealth = async () => {
      setIsChecking(true);
      let retries = 0;
      const maxRetries = 10;
      const initialDelay = 1000;

      const attemptConnection = async (): Promise<boolean> => {
        try {
          const response = await fetch(
            `${process.env.NEXT_PUBLIC_BACKEND_URL}/health`,
            {
              method: "GET",
              signal: AbortSignal.timeout(5000),
            }
          );

          if (!response.ok) {
            throw new Error(`Health check returned ${response.status}`);
          }

          console.log("✅ Backend server is healthy");
          setIsHealthy(true);
          setIsChecking(false);
          return true;
        } catch (error) {
          retries++;
          if (retries < maxRetries) {
            const delayMs = initialDelay * Math.pow(2, retries - 1);
            console.warn(
              `⏳ Backend not ready (attempt ${retries}/${maxRetries}). Retrying in ${delayMs}ms...`,
              error
            );
            await new Promise((resolve) => setTimeout(resolve, delayMs));
            return attemptConnection();
          } else {
            console.error(
              "❌ Backend failed to respond after 10 retries. Proceeding anyway."
            );
            setIsHealthy(true); // Fallback: proceed anyway
            setIsChecking(false);
            return false;
          }
        }
      };

      await attemptConnection();
    };

    checkHealth();
  }, []);

  return { isHealthy, isChecking };
}
