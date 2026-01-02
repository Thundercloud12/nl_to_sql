"use client";

import { useState, useEffect, useRef, use } from "react";
import { useUser, UserButton } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  Loader2,
  AlertCircle,
  ArrowLeft,
  Terminal,
  Zap,
  Cpu,
  ChevronDown,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useServerHealth } from "@/hooks/useServerHealth";

import { ThemeToggle } from "@/components/theme-toggle";

import { Chart } from "@/components/Chart";  // ✅ ADD: Import Chart component


/* ----------------------------- Types ----------------------------- */

interface Message {
  role: "user" | "assistant";
  content: string;
  insight?: string;
  chart?: any;  // ✅ ADD: Chart data (Plotly JSON)
}

interface ClarificationState {
  status: "need_clarification";
  question: string;
  all_questions: string[];
  session_id: string;
}

interface ChatPageProps {
  searchParams: Promise<{
    dataSourceId?: string;
    sessionId?: string;
  }>;
}

/* ----------------------------- Component ----------------------------- */

export default function ChatPage({ searchParams }: ChatPageProps) {
  const { user } = useUser();
  const router = useRouter();
  const params = use(searchParams);
  const { isHealthy, isChecking } = useServerHealth();

  const dataSourceId = params.dataSourceId;
  const sessionIdFromUrl = params.sessionId;

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [userInput, setUserInput] = useState("");
  const [datasourceType, setDatasourceType] = useState<string>("file");
  const [datasourceName, setDatasourceName] = useState<string>("");

  const [clarification, setClarification] =
    useState<ClarificationState | null>(null);
  const [clarificationInput, setClarificationInput] = useState("");

  const [expandedMessages, setExpandedMessages] = useState<Set<number>>(
    new Set()
  );

  const initializedRef = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  /* ----------------------------- Auto Scroll ----------------------------- */

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  /* ----------------------------- Session Init ----------------------------- */

  useEffect(() => {
    if (!user || !dataSourceId) return;
    if (initializedRef.current) return;

    initializedRef.current = true;

    const initSession = async () => {
      try {
        setLoading(true);

        const endpoint = "/initialize_chat";

        const response = await fetch(
          `${process.env.NEXT_PUBLIC_BACKEND_URL}${endpoint}`,
          {
            method: "POST",
            cache: "no-store",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              session_id: sessionIdFromUrl,
              data_source_id: dataSourceId,
              user_id: user.id,
            }),
          }
        );

        if (!response.ok) {
          throw new Error("Failed to initialize session");
        }

        const data = await response.json();

        setSessionId(data.session_id);
        
        // Fetch datasource info to detect type
        if (data.data_source) {
          const metadata = data.data_source.rawMetadata || {};
          setDatasourceType(metadata.type || "file");
          setDatasourceName(metadata.connection_name || data.data_source.cloudinaryUrl?.split('/').pop() || "Unknown");
        }

        if (data.conversation_history) {
          const msgs =
            data.conversation_history.messages ||
            data.conversation_history;

          const hydrated: Message[] = msgs.map((m: any) => ({
            role: m.role,
            content: m.content,
            insight: m.role === "assistant" ? m.insights : undefined,
            chart: m.chart || null,  // ✅ RESTORE: Chart data from saved session
          }));

          setMessages(hydrated);
        }
      } catch (err: any) {
        setError(err.message || "Initialization failed");
      } finally {
        setLoading(false);
      }
    };

    initSession();
  }, [user, dataSourceId, sessionIdFromUrl]);

  /* ----------------------------- Send Message ----------------------------- */

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!userInput.trim() || !sessionId || loading) return;

    const question = userInput;
    setUserInput("");
    setLoading(true);

    setMessages((prev) => [...prev, { role: "user", content: question }]);

    try {
      const endpoint = messages.length === 0 ? "/query" : "/continue";

      const response = await fetch(
        `${process.env.NEXT_PUBLIC_BACKEND_URL}${endpoint}`,
        {
          method: "POST",
          cache: "no-store",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question,
            session_id: sessionId,
            user_id: user?.id,
            data_source_id: dataSourceId,
          }),
        }
      );

      const data = await response.json();

      if (data.status === "need_clarification") {
        setClarification(data);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.answer || "",
            insight: data.insights,
            chart: data.chart || null,  // ✅ ADD: Chart data
          },
        ]);
      }
    } catch {
      setError("Failed to send message");
    } finally {
      setLoading(false);
    }
  };

  /* ----------------------------- Clarification ----------------------------- */

  const handleClarificationSubmit = async () => {
    if (!clarificationInput.trim() || loading || !clarification) return;

    setLoading(true);
    setClarification(null);

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_BACKEND_URL}/clarify`,
        {
          method: "POST",
          cache: "no-store",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: clarification.session_id,
            answer: clarificationInput,
          }),
        }
      );

      const data = await response.json();

      if (data.status === "need_clarification") {
        setClarification(data);
      } else {
        setMessages((prev) => [
          ...prev,
          { role: "user", content: clarificationInput },
          {
            role: "assistant",
            content: data.answer || "",
            insight: data.insights,
            chart: data.chart || null,  // ✅ ADD: Chart data
          },
        ]);
      }

      setClarificationInput("");
    } catch {
      setError("Clarification failed");
    } finally {
      setLoading(false);
    }
  };

  /* ----------------------------- UI Helpers ----------------------------- */

  const toggleExpansion = (idx: number) => {
    setExpandedMessages((prev) => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  };

   const handleBackToDashboard = async () => {
    if (!sessionId) {
      router.push("/dashboard");
      return;
    }

    try {
      // Save session before leaving
      await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/save_session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          user_id: user?.id,
          data_source_id: dataSourceId,
          conversation_history: messages.map(m => ({
            role: m.role,
            content: m.role === "assistant"
              ? (m.insight || m.content)
              : m.content,
            chart: m.chart || null  // ✅ INCLUDE: Chart data for persistence
          }))
        }),
      });
      console.log("[CHAT] Session saved and cleanup completed");
    } catch (err) {
      console.error("[CHAT] Failed to save session:", err);
    } finally {
      router.push("/dashboard");
    }
  };

  /* ----------------------------- Render ----------------------------- */

  return (
   <div className="min-h-screen bg-background text-foreground flex flex-col font-sans">
      {/* Health Check Loading State */}
      {isChecking && (
        <div className="fixed inset-0 flex flex-col items-center justify-center bg-background/95 backdrop-blur-md z-50">
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="text-center"
          >
            <div className="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mx-auto mb-6 border border-[#00e599]/30 shadow-[0_0_30px_-10px_rgba(0,229,153,0.3)]">
              <Loader2 className="w-8 h-8 text-[#00e599] animate-spin" />
            </div>
            <h2 className="text-2xl font-bold text-foreground mb-2">Warming up backend...</h2>
            <p className="text-muted-foreground max-w-sm mx-auto mb-6">
              Initializing server connection. This may take a moment.
            </p>
            <div className="flex gap-2 justify-center">
              <div className="w-2 h-2 bg-[#00e599] rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
              <div className="w-2 h-2 bg-[#00e599] rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
              <div className="w-2 h-2 bg-[#00e599] rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
          </motion.div>
        </div>
      )}

      {/* Page Content - Hidden while checking */}
      {!isChecking && (
        <>
      {/* Background Effect */}
      <div className="fixed inset-0 pointer-events-none opacity-20">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:32px_32px]"></div>
      </div>

      {/* Header */}
      <header className="sticky top-0 z-50 bg-background/80 backdrop-blur-xl border-b border-border px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button 
              variant="ghost" 
              onClick={handleBackToDashboard}  // ✅ CHANGE THIS
              className="text-muted-foreground hover:text-foreground p-0 h-auto"
            >
              <ArrowLeft size={20} />
            </Button>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-bold tracking-tight">AI Data Agent</h1>
                <div className="px-2 py-0.5 rounded-full bg-[#00e599]/10 text-[#00e599] text-[10px] font-mono border border-[#00e599]/20 flex items-center gap-1">
                  <div className="w-1 h-1 bg-[#00e599] rounded-full animate-pulse" />
                  {datasourceType === "postgres" ? "POSTGRES_LIVE" : "LIVE_SYNC"}
                </div>
              </div>
              <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest mt-0.5">
                {datasourceType === "postgres" ? "🐘 PostgreSQL" : "📄 File"} • Session: {sessionId?.slice(0, 8) || "Initialising"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
             <div className="hidden md:flex flex-col items-end mr-2">
                <span className="text-[10px] text-muted-foreground font-mono">
                  {datasourceType === "postgres" ? "READ-ONLY" : "ENCRYPTION"}
                </span>
                <span className="text-[10px] text-[#00e599] font-mono flex items-center gap-1">
                   <ShieldCheck size={10} /> {datasourceType === "postgres" ? "SQL_GUARD" : "AES-256"}
                </span>
             </div>
             <ThemeToggle />
             <UserButton appearance={{ elements: { avatarBox: "w-8 h-8 border border-border" } }} />
          </div>
        </div>
      </header>

      {/* Message Feed */}
      <main className="flex-1 overflow-y-auto relative z-10 px-4">
        <div className="max-w-4xl mx-auto py-12 space-y-8">
          <AnimatePresence mode="popLayout">
            {messages.length === 0 && !loading && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center py-20">
                    <div className="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mx-auto mb-6 border border-border">
                        <Terminal className="text-[#00e599]" size={32} />
                    </div>
                    <h2 className="text-2xl font-bold text-foreground mb-2">Awaiting Instructions</h2>
                    <p className="text-muted-foreground max-w-sm mx-auto">Ask a question about the uploaded dataset. The AI will analyze schema and provide insights.</p>
                </motion.div>
            )}

            {messages.map((msg, idx) => (
              <motion.div
                key={idx}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={cn(
                  "flex flex-col",
                  msg.role === "user" ? "items-end" : "items-start"
                )}
              >
                <div className={cn(
                  "max-w-[85%] group relative",
                  msg.role === "user" ? "order-1" : "order-2"
                )}>
                  {/* User Message */}
                  {msg.role === "user" ? (
                    <div className="bg-[#00e599] text-black font-medium px-6 py-3 rounded-2xl rounded-tr-none shadow-[0_10px_30px_-10px_rgba(0,229,153,0.3)]">
                      {msg.content}
                    </div>
                  ) : (
                    /* Assistant Message */
                    <div className={cn(
                        "bg-card border border-border backdrop-blur-md px-6 py-4 rounded-2xl rounded-tl-none",
                        msg.insight && "border-[#00e599]/30 shadow-[0_0_40px_-10px_rgba(0,229,153,0.1)]"
                    )}>
                      {msg.insight && (
                        <div className="flex items-center gap-2 text-[#00e599] text-[10px] font-mono font-bold uppercase tracking-widest mb-3">
                          <Zap size={12} fill="currentColor" />
                          AI Synthesized Insight
                        </div>
                      )}
                      
                      <div className="text-sm leading-relaxed text-foreground whitespace-pre-wrap">
                        {msg.insight || msg.content}
                      </div>

                      {/* ✅ ADD: Render chart if available */}
                      {msg.chart && <Chart data={msg.chart} />}

                      {msg.insight && (
                        <div className="mt-4 pt-4 border-t border-border">
                          <button 
                            onClick={() => toggleExpansion(idx)}
                            className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
                          >
                            <Cpu size={12} />
                            {expandedMessages.has(idx) ? "Hide technical output" : "Show technical output"}
                            <ChevronDown size={12} className={cn("transition-transform", expandedMessages.has(idx) && "rotate-180")} />
                          </button>
                          
                          <AnimatePresence>
                            {expandedMessages.has(idx) && (
                              <motion.div 
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: "auto", opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                className="overflow-hidden"
                              >
                                <div className="mt-3 p-3 bg-muted rounded-lg border border-border text-[12px] font-mono text-muted-foreground leading-relaxed">
                                  {msg.content}
                                </div>
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </motion.div>
            ))}

            {/* Thinking State */}
            {loading && !clarification && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-muted border border-border flex items-center justify-center">
                  <Loader2 size={14} className="animate-spin text-[#00e599]" />
                </div>
                <div className="flex gap-1">
                   {[0, 1, 2].map(i => (
                     <div key={i} className="w-1.5 h-1.5 bg-[#00e599] rounded-full animate-bounce" style={{ animationDelay: `${i*150}ms` }} />
                   ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>

      {/* Footer Input */}
      <footer className="p-6 bg-gradient-to-t from-[#0D0E12] via-[#0D0E12] to-transparent">
        <div className="max-w-4xl mx-auto">
          {clarification ? (
            <motion.div initial={{ y: 20 }} animate={{ y: 0 }} className="bg-card border border-amber-500/30 p-6 rounded-2xl mb-4 shadow-[0_0_30px_-10px_rgba(245,158,11,0.2)]">
               <h3 className="text-amber-500 text-xs font-bold uppercase tracking-widest mb-2 flex items-center gap-2">
                 <AlertCircle size={14} /> Clarification Needed
               </h3>
               <p className="text-sm mb-6 text-foreground">{clarification.question}</p>
               <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-4">
                  {clarification.all_questions.map((q, i) => (
                    <button 
                        key={i} 
                        onClick={() => { setClarificationInput(q); }}
                        className="text-left px-4 py-2 text-xs bg-muted border border-border hover:border-[#00e599] rounded-lg transition-all"
                    >
                      {q}
                    </button>
                  ))}
               </div>
               <div className="flex gap-2">
                  <Input 
                    className="bg-card border-border rounded-xl"
                    placeholder="Type detail..."
                    value={clarificationInput}
                    onChange={(e) => setClarificationInput(e.target.value)}
                  />
                  <Button 
                    onClick={handleClarificationSubmit}  // ✅ CHANGE THIS
                    disabled={loading || !clarificationInput.trim()}
                    className="bg-[#00e599] text-black hover:bg-[#00e599]/80"
                  >
                    {loading ? <Loader2 className="animate-spin" /> : "Reply"}
                  </Button>
               </div>
            </motion.div>
          ) : (
            <form onSubmit={handleSendMessage} className="relative group">
               <div className="absolute -inset-1 bg-gradient-to-r from-[#00e599] to-cyan-500 rounded-2xl blur opacity-10 group-focus-within:opacity-30 transition-opacity" />
               <div className="relative flex items-center bg-card border border-border rounded-2xl p-2 pr-3 focus-within:border-[#00e599]/50 transition-all shadow-2xl">
                  <div className="pl-4 text-muted-foreground"><Terminal size={18} /></div>
                  <Input 
                    value={userInput}
                    onChange={(e) => setUserInput(e.target.value)}
                    placeholder="Ask about trends, patterns, or specific data points..."
                    className="bg-transparent border-none focus-visible:ring-0 text-foreground placeholder:text-muted-foreground h-12"
                    disabled={loading}
                  />
                  <Button 
                    type="submit" 
                    disabled={loading || !userInput.trim()}
                    className="bg-[#00e599] text-black font-bold rounded-xl h-10 px-6 hover:bg-[#00e599]/90 disabled:bg-muted disabled:text-muted-foreground"
                  >
                    {loading ? <Loader2 className="animate-spin w-4 h-4" /> : "Analyze"}
                  </Button>
               </div>
            </form>
          )}
          
          <p className="text-center text-[10px] text-muted-foreground mt-4 uppercase tracking-[0.2em] font-mono">
            AI can make mistakes. Verify critical data.
          </p>
        </div>
      </footer>
        </>
      )}
    </div>
  );
}
