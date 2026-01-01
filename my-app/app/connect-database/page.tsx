"use client";

import { useState } from "react";
import { useUser } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Database, Loader2, CheckCircle, XCircle, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useServerHealth } from "@/hooks/useServerHealth";

export default function ConnectDatabasePage() {
  const { user } = useUser();
  const router = useRouter();
  const { serverStatus, isChecking } = useServerHealth();
  
  const [formData, setFormData] = useState({
    host: "",
    port: "5432",
    database: "",
    username: "",
    password: "",
    displayName: ""
  });
  
  const [testing, setTesting] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [testResult, setTestResult] = useState<{success: boolean, message: string} | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData(prev => ({
      ...prev,
      [e.target.name]: e.target.value
    }));
    setTestResult(null);
    setError(null);
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    setError(null);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/test_db_connection`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          host: formData.host,
          port: parseInt(formData.port),
          database: formData.database,
          username: formData.username,
          password: formData.password,
          user_id: user?.id
        })
      });

      const data = await response.json();
      setTestResult(data);
      
      if (!data.success) {
        setError(data.message);
      }
    } catch (err: any) {
      setError(err.message || "Failed to test connection");
      setTestResult({ success: false, message: "Connection test failed" });
    } finally {
      setTesting(false);
    }
  };

  const handleConnect = async () => {
    if (!testResult?.success) {
      setError("Please test the connection first");
      return;
    }

    setConnecting(true);
    setError(null);

    try {
      const response = await fetch("/api/datasources/connect-db", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...formData,
          port: parseInt(formData.port),
          user_id: user?.id
        })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Failed to connect database");
      }

      router.push("/dashboard");
    } catch (err: any) {
      setError(err.message || "Failed to connect database");
    } finally {
      setConnecting(false);
    }
  };

  if (!user || isChecking) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="w-10 h-10 animate-spin text-[#00e599]" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground pt-24 pb-12 px-4 sm:px-6 lg:px-8">
      <div className="fixed inset-0 z-0 pointer-events-none dark:block hidden">
        <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-[#00e599]/5 blur-[120px]" />
      </div>

      <div className="max-w-2xl mx-auto relative z-10">
        <Button
          variant="ghost"
          onClick={() => router.push("/dashboard")}
          className="text-muted-foreground hover:text-[#00e599] hover:bg-[#00e599]/5 transition-all mb-6 px-0"
        >
          <ArrowLeft className="mr-2" size={18} />
          Back to Dashboard
        </Button>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <h1 className="text-4xl font-bold tracking-tight mb-2">
            Connect PostgreSQL Database
          </h1>
          <p className="text-muted-foreground">
            Connect your PostgreSQL database and query it using natural language
          </p>
        </motion.div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database className="text-[#00e599]" size={24} />
              Database Credentials
            </CardTitle>
            <CardDescription>
              Enter your PostgreSQL database connection details
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {error && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 text-sm text-red-500">
                {error}
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-2">Host</label>
                <Input
                  name="host"
                  value={formData.host}
                  onChange={handleInputChange}
                  placeholder="localhost"
                  disabled={testing || connecting}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Port</label>
                <Input
                  name="port"
                  value={formData.port}
                  onChange={handleInputChange}
                  placeholder="5432"
                  disabled={testing || connecting}
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Database Name</label>
              <Input
                name="database"
                value={formData.database}
                onChange={handleInputChange}
                placeholder="my_database"
                disabled={testing || connecting}
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Username</label>
              <Input
                name="username"
                value={formData.username}
                onChange={handleInputChange}
                placeholder="postgres"
                disabled={testing || connecting}
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Password</label>
              <Input
                name="password"
                type="password"
                value={formData.password}
                onChange={handleInputChange}
                placeholder="••••••••"
                disabled={testing || connecting}
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Display Name (Optional)</label>
              <Input
                name="displayName"
                value={formData.displayName}
                onChange={handleInputChange}
                placeholder="Production Database"
                disabled={testing || connecting}
              />
            </div>

            {testResult && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex items-center gap-2 p-4 rounded-lg border ${
                  testResult.success
                    ? "bg-green-500/10 border-green-500/20 text-green-500"
                    : "bg-red-500/10 border-red-500/20 text-red-500"
                }`}
              >
                {testResult.success ? (
                  <CheckCircle size={20} />
                ) : (
                  <XCircle size={20} />
                )}
                <span className="text-sm font-medium">{testResult.message}</span>
              </motion.div>
            )}

            <div className="flex gap-3 pt-4">
              <Button
                onClick={handleTestConnection}
                disabled={!formData.host || !formData.database || !formData.username || testing || connecting}
                variant="outline"
                className="flex-1"
              >
                {testing ? (
                  <>
                    <Loader2 className="mr-2 animate-spin" size={16} />
                    Testing...
                  </>
                ) : (
                  "Test Connection"
                )}
              </Button>

              <Button
                onClick={handleConnect}
                disabled={!testResult?.success || connecting}
                className="flex-1 bg-[#00e599] text-black hover:bg-[#00e599]/90"
              >
                {connecting ? (
                  <>
                    <Loader2 className="mr-2 animate-spin" size={16} />
                    Connecting...
                  </>
                ) : (
                  "Connect Database"
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="mt-8 p-4 bg-muted rounded-lg">
          <h3 className="font-medium mb-2">Security Note</h3>
          <p className="text-sm text-muted-foreground">
            Your database credentials are stored securely. We recommend using a read-only database user with limited permissions for maximum security.
          </p>
        </div>
      </div>
    </div>
  );
}
