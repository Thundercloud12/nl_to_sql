"use client";

import { useState, useEffect } from "react";
import { useUser } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { 
  Plus, 
  Database, 
  Calendar, 
  Trash2, 
  MessageSquare, 
  FileSpreadsheet, 
  Loader2,
  ExternalLink,
  ChevronRight,
  Activity
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface DataSource {
  id: string;
  userId: string;
  cloudinaryUrl: string;
  createdAt: string;
  rawMetadata?: {
    type?: string;
    connection_name?: string;
    allowed_tables?: string[];
  };
}

export default function DashboardPage() {
  const { user } = useUser();
  const router = useRouter();
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [startingChatId, setStartingChatId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false); // Add this state

  useEffect(() => {
    if (!user) return;
    fetchDataSources();
  }, [user]);

  const fetchDataSources = async () => {
    try {
      setLoading(true);
      const response = await fetch("/api/datasources/list");
      if (!response.ok) throw new Error("Failed to fetch data sources");
      const data = await response.json();
      setDataSources(data.dataSources || []);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleStartChat = async (dataSourceId: string) => {
    try {
      setStartingChatId(dataSourceId);
      const backendResponse = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/initialize_chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          data_source_id: dataSourceId,
          user_id: user?.id,
        }),
      });

      if (!backendResponse.ok) throw new Error("Failed to initialize chat");
      const backendData = await backendResponse.json();
      router.push(`/chat?dataSourceId=${dataSourceId}&sessionId=${backendData.session_id}`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setStartingChatId(null);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure? This will permanently erase this data source and all AI memory associated with it.")) return;

    try {
      setDeleting(true); // Show loading screen
      const response = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/datasource/${id}?user_id=${user?.id}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error("Failed to delete data source");
      await fetchDataSources();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setDeleting(false); // Hide loading screen
    }
  };

  const getFileName = (url: string) => {
    const parts = url.split("/");
    const filename = parts[parts.length - 1] || "Unknown File";
    return filename.length > 25 ? filename.slice(0, 22) + "..." : filename;
  };

  const getDataSourceName = (ds: DataSource) => {
    if (ds.rawMetadata?.type === "postgres") {
      return ds.rawMetadata.connection_name || "PostgreSQL Database";
    }
    return getFileName(ds.cloudinaryUrl);
  };

  const getDataSourceIcon = (ds: DataSource) => {
    if (ds.rawMetadata?.type === "postgres") {
      return Database;
    }
    return FileSpreadsheet;
  };

  if (!user) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="w-10 h-10 animate-spin text-[#00e599]" />
      </div>
    );
  }

  // Add loading screen when deleting
  if (deleting) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-12 h-12 animate-spin text-[#00e599] mx-auto mb-4" />
          <p className="text-foreground font-medium">Deleting data source...</p>
          <p className="text-muted-foreground text-sm mt-2">This may take a few moments</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground pt-24 pb-12 px-4 sm:px-6 lg:px-8">
      {/* Background Decor */}
      <div className="fixed inset-0 z-0 pointer-events-none dark:block hidden">
        <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-[#00e599]/5 blur-[120px]" />
      </div>

      <div className="max-w-7xl mx-auto relative z-10">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-12">
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
          >
            <div className="flex items-center gap-2 text-[#00e599] font-mono text-xs mb-3 uppercase tracking-widest">
              <Activity size={14} />
              <span>System / Data Manager</span>
            </div>
            <h1 className="text-4xl font-bold tracking-tight text-foreground">
              Datasets
            </h1>
          </motion.div>

          <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
            <div className="flex gap-3">
              <Button
                onClick={() => router.push("/upload-file")}
                className="bg-[#00e599] text-black hover:bg-[#00e599]/90 font-bold rounded-lg px-8 h-12 shadow-[0_0_20px_-5px_#00e599]"
              >
                <Plus className="w-5 h-5 mr-2" />
                Upload File
              </Button>
              <Button
                onClick={() => router.push("/connect-postgres")}
                variant="outline"
                className="border-[#00e599]/30 hover:bg-[#00e599]/10 font-bold rounded-lg px-8 h-12"
              >
                <Database className="w-5 h-5 mr-2" />
                Connect PostgreSQL
              </Button>
            </div>
          </motion.div>
        </div>

        {/* Error State */}
        {error && (
          <div className="mb-8 p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm flex items-center gap-3">
            <span className="flex-1">⚠️ {error}</span>
            <button onClick={() => setError(null)} className="hover:text-foreground underline">Dismiss</button>
          </div>
        )}

        {/* Loading / Skeletons */}
        {loading && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-64 rounded-2xl bg-white/5 border border-white/5 animate-pulse" />
            ))}
          </div>
        )}

        {/* Empty State */}
        {!loading && dataSources.length === 0 && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex flex-col items-center justify-center py-20 border-2 border-dashed border-white/5 rounded-[2rem] bg-white/[0.02]"
          >
            <div className="w-20 h-20 bg-zinc-900 rounded-3xl flex items-center justify-center mb-6 text-zinc-600">
              <Database size={40} />
            </div>
            <h3 className="text-xl font-bold mb-2">No active sources found</h3>
            <p className="text-zinc-500 mb-8 max-w-xs text-center">
              Connect a CSV or Excel file to begin training your AI agent on your data.
            </p>
            <Button variant="outline" onClick={() => router.push("/upload-file")} className="border-white/10 hover:bg-white/5">
              Get Started
            </Button>
          </motion.div>
        )}

        {/* Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {dataSources.map((ds, index) => {
            const IconComponent = getDataSourceIcon(ds);
            const isPostgres = ds.rawMetadata?.type === "postgres";
            
            return (
            <motion.div
              key={ds.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05 }}
            >
              <Card className="bg-zinc-900/40 border-white/5 hover:border-[#00e599]/30 transition-all duration-300 overflow-hidden group">
                <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-[#00e599]/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                
                <CardHeader className="pb-4">
                  <div className="flex justify-between items-start mb-4">
                    <div className="p-3 bg-muted rounded-xl text-[#00e599] group-hover:bg-[#00e599] group-hover:text-black transition-colors duration-300">
                      <IconComponent size={24} />
                    </div>
                    <div className="text-[10px] font-mono text-zinc-600 uppercase tracking-widest">
                      {isPostgres ? "Live" : "Ready"}
                    </div>
                  </div>
                  <CardTitle className="text-lg font-bold text-foreground group-hover:text-foreground transition-colors truncate">
                    {getDataSourceName(ds)}
                  </CardTitle>
                  <CardDescription className="text-zinc-500 font-mono text-[11px] flex items-center gap-2">
                    <Calendar size={12} />
                    {new Date(ds.createdAt).toLocaleDateString()}
                  </CardDescription>
                  {isPostgres && ds.rawMetadata?.allowed_tables && (
                    <div className="mt-2 text-[10px] text-zinc-600 font-mono">
                      {ds.rawMetadata.allowed_tables.length} tables accessible
                    </div>
                  )}
                </CardHeader>
                
                <CardContent>
                    <div className="p-3 bg-black/40 rounded-lg border border-white/5 flex items-center justify-between">
                        <span className="text-[10px] font-mono text-zinc-500 italic">
                          {isPostgres ? "POSTGRES" : "FILE"} • {ds.id.slice(0, 8)}
                        </span>
                        <ExternalLink size={12} className="text-zinc-700" />
                    </div>
                </CardContent>

                <CardFooter className="flex gap-2 pt-2">
                  <Button
                    onClick={() => handleStartChat(ds.id)}
                    disabled={startingChatId === ds.id}
                    className={cn(
                        "flex-1 font-bold transition-all",
                        startingChatId === ds.id 
                            ? "bg-zinc-800 text-zinc-500" 
                            : "bg-foreground text-background hover:bg-[#00e599]"
                    )}
                    size="sm"
                  >
                    {startingChatId === ds.id ? (
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    ) : (
                      <MessageSquare className="w-4 h-4 mr-2" />
                    )}
                    {startingChatId === ds.id ? "Initializing..." : "Query Data"}
                  </Button>
                  
                  <Button
                    onClick={() => handleDelete(ds.id)}
                    variant="ghost"
                    size="sm"
                    className="text-zinc-600 hover:text-red-400 hover:bg-red-400/10 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </CardFooter>
              </Card>
            </motion.div>
            );
          })}
        </div>

        {/* Stats Section / Footer Info */}
        {!loading && dataSources.length > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
            className="mt-16 border-t border-white/5 pt-8 flex flex-col md:flex-row justify-between items-center gap-4"
          >
            <div className="flex items-center gap-8">
                <div>
                    <p className="text-xs text-zinc-500 font-mono uppercase mb-1">Active Sources</p>
                    <p className="text-2xl font-bold">{dataSources.length}</p>
                </div>
                <div className="h-8 w-px bg-white/10" />
                <div>
                    <p className="text-xs text-zinc-500 font-mono uppercase mb-1">Storage Status</p>
                    <p className="text-2xl font-bold text-[#00e599]">Optimized</p>
                </div>
            </div>
            <p className="text-xs text-zinc-600 font-mono">
                System: AI Inference Engine v2.4.0-stable
            </p>
          </motion.div>
        )}
      </div>
    </div>
  );
}