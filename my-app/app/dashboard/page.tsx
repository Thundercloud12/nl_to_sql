"use client";

import { useState, useEffect } from "react";
import { useUser } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Plus, Database, Calendar, Trash2, MessageSquare, FileSpreadsheet, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";

interface DataSource {
  id: string;
  userId: string;
  cloudinaryUrl: string;
  createdAt: string;
}

export default function DashboardPage() {
  const { user } = useUser();
  const router = useRouter();
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [startingChatId, setStartingChatId] = useState<string | null>(null); // ✅ ADD: Track which chat is starting

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
      setStartingChatId(dataSourceId); // ✅ ADD: Set loading state
      
      // Initialize chat session with backend
      const backendResponse = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/initialize_chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          data_source_id: dataSourceId,
          user_id: user?.id,
        }),
      });

      if (!backendResponse.ok) {
        throw new Error("Failed to initialize chat");
      }

      const backendData = await backendResponse.json();
      
      // Navigate to chat with session info
      router.push(`/chat?dataSourceId=${dataSourceId}&sessionId=${backendData.session_id}`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setStartingChatId(null); // ✅ ADD: Clear loading state
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to delete this data source? This will also delete all associated sessions and conversations.")) return;

    try {
      setLoading(true);
      const response = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/datasource/${id}?user_id=${user?.id}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Failed to delete data source");
      }

      const data = await response.json();
      console.log(`Deleted: ${data.deleted_sessions} sessions, ${data.deleted_conversations} conversations`);
      
      // Refresh the list
      await fetchDataSources();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const getFileName = (url: string) => {
    const parts = url.split("/");
    const filename = parts[parts.length - 1] || "Unknown File";
    return filename.length > 30 ? filename.slice(0, 27) + "..." : filename;
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Card className="p-8 max-w-md">
          <CardContent className="text-center">
            <Loader2 className="w-12 h-12 animate-spin text-primary mx-auto mb-4" />
            <p className="text-lg text-muted-foreground">Loading...</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen py-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-4xl font-bold text-foreground mb-2">
                Your Data Sources
              </h1>
              <p className="text-lg text-muted-foreground">
                Manage your uploaded datasets and start conversations
              </p>
            </div>
            <Button
              onClick={() => router.push("/upload-file")}
              size="lg"
              className="group w-full sm:w-auto"
            >
              <Plus className="w-5 h-5 mr-2 group-hover:rotate-90 transition-transform" />
              Upload New
            </Button>
          </div>
        </motion.div>

        {/* Error Display */}
        {error && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="mb-6"
          >
            <Card className="border-error/50 bg-error/10">
              <CardContent className="pt-6">
                <p className="text-error font-medium">⚠️ {error}</p>
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3].map((i) => (
              <Card key={i} className="animate-pulse">
                <CardHeader>
                  <div className="h-6 bg-muted rounded w-3/4 mb-2"></div>
                  <div className="h-4 bg-muted rounded w-1/2"></div>
                </CardHeader>
                <CardContent>
                  <div className="h-4 bg-muted rounded w-full"></div>
                </CardContent>
                <CardFooter>
                  <div className="h-10 bg-muted rounded w-full"></div>
                </CardFooter>
              </Card>
            ))}
          </div>
        )}

        {/* Empty State */}
        {!loading && dataSources.length === 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center py-16"
          >
            <Card className="max-w-md mx-auto p-8 border-dashed border-2">
              <CardContent className="space-y-4">
                <div className="w-20 h-20 bg-muted rounded-full flex items-center justify-center mx-auto">
                  <Database className="w-10 h-10 text-muted-foreground" />
                </div>
                <h3 className="text-2xl font-semibold text-foreground">
                  No Data Sources Yet
                </h3>
                <p className="text-muted-foreground">
                  Upload your first dataset to start asking questions and getting AI-powered insights
                </p>
                <Button
                  onClick={() => router.push("/upload-file")}
                  size="lg"
                  className="mt-4"
                >
                  <Plus className="w-5 h-5 mr-2" />
                  Upload Data Source
                </Button>
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* Data Sources Grid */}
        {!loading && dataSources.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {dataSources.map((ds, index) => (
              <motion.div
                key={ds.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1 }}
              >
                <Card className="h-full hover:shadow-2xl transition-all duration-300 hover:-translate-y-1 group">
                  <CardHeader>
                    <div className="flex items-start justify-between mb-4">
                      <div className="w-14 h-14 bg-gradient-to-br from-primary to-accent rounded-xl flex items-center justify-center shadow-lg group-hover:scale-110 transition-transform">
                        <FileSpreadsheet className="w-7 h-7 text-white" />
                      </div>
                    </div>
                    <CardTitle className="text-xl line-clamp-2 text-foreground">
                      {getFileName(ds.cloudinaryUrl)}
                    </CardTitle>
                    <CardDescription className="flex items-center text-sm mt-2">
                      <Calendar className="w-4 h-4 mr-1.5" />
                      {formatDate(ds.createdAt)}
                    </CardDescription>
                  </CardHeader>
                  
                  <CardContent>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">ID:</span>
                      <code className="text-xs bg-muted px-2 py-1 rounded font-mono">
                        {ds.id.slice(0, 12)}...
                      </code>
                    </div>
                  </CardContent>

                  <CardFooter className="flex gap-2">
                    <Button
                      onClick={() => handleStartChat(ds.id)}
                      disabled={startingChatId === ds.id} // ✅ ADD: Disable while loading
                      className="flex-1 group/btn"
                      size="sm"
                    >
                      {startingChatId === ds.id ? ( // ✅ ADD: Show spinner when loading
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      ) : (
                        <MessageSquare className="w-4 h-4 mr-2 group-hover/btn:scale-110 transition-transform" />
                      )}
                      {startingChatId === ds.id ? "Starting..." : "Start Chat"} {/* ✅ ADD: Change text */}
                    </Button>
                    <Button
                      onClick={() => handleDelete(ds.id)}
                      variant="outline"
                      size="sm"
                      className="text-error hover:bg-error/10 hover:border-error/50 border-border"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </CardFooter>
                </Card>
              </motion.div>
            ))}
          </div>
        )}

        {/* Stats Section */}
        {!loading && dataSources.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="mt-12"
          >
            <Card className="bg-gradient-to-br from-primary/10 to-accent/10 border-primary/20">
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground mb-1">Total Data Sources</p>
                    <p className="text-3xl font-bold text-foreground">{dataSources.length}</p>
                  </div>
                  <div className="w-16 h-16 bg-primary/20 rounded-full flex items-center justify-center">
                    <Database className="w-8 h-8 text-primary" />
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </div>
    </div>
  );
}
