"use client";

import { useState, useEffect, useRef, use } from "react";
import { useUser, UserButton } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Loader2, AlertCircle, Lightbulb, X, ArrowLeft, Bot, User as UserIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";

interface Message {
  role: "user" | "assistant" | "insight";
  content: string;
}

interface ClarificationState {
  status: "need_clarification";
  question: string;
  all_questions: string[];
  session_id: string;
}

// ✅ FIX: searchParams is a Promise, not an object
interface ChatPageProps {
  searchParams: Promise<{
    dataSourceId?: string;
    sessionId?: string;
  }>;
}

// ✅ CHANGED: Accept searchParams as prop
export default function ChatPage({ searchParams }: ChatPageProps) {
  const { user } = useUser();
  const router = useRouter();
  
  // ✅ FIX: Unwrap the Promise using React.use()
  const params = use(searchParams);
  const dataSourceId = params.dataSourceId;
  const sessionId = params.sessionId;
  
  const [session, setSession] = useState<any>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [userInput, setUserInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clarification, setClarification] = useState<ClarificationState | null>(null);
  const [clarificationInput, setClarificationInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Initialize session on mount and load conversation history
  useEffect(() => {
    if (!user || !dataSourceId || !sessionId) return;

    const initSession = async () => {
      try {
        setLoading(true);
        
        // Re-initialize chat to get conversation history
        const response = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/initialize_chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            data_source_id: dataSourceId,
            user_id: user?.id,
          }),
        });

        if (!response.ok) {
          throw new Error("Failed to load chat session");
        }

        const data = await response.json();
        
        setSession({
          id: data.session_id,
          conversationHistory: data.conversation_history || [],
          lastResult: data.last_result,
          lastPlan: data.last_plan,
        });

        // Load existing conversation history into messages
        if (data.conversation_history && data.conversation_history.length > 0) {
          const loadedMessages: Message[] = data.conversation_history.map((msg: any) => ({
            role: msg.role as "user" | "assistant" | "insight",
            content: msg.content,
          }));
          setMessages(loadedMessages);
          console.log(`[CHAT] Loaded ${loadedMessages.length} previous messages`);
        }
      } catch (err: any) {
        setError(err.message);
        console.error("Error loading session:", err);
      } finally {
        setLoading(false);
      }
    };

    initSession();
  }, [user, dataSourceId, sessionId]);

  // Send message
  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!userInput.trim() || !session || !dataSourceId) return;

    const currentInput = userInput;
    setUserInput("");
    setLoading(true);
    setError(null);

    // Add user message immediately for better UX
    setMessages((prev) => [...prev, { role: "user", content: currentInput }]);

    try {
      const isFirstMessage = messages.length === 0;
      const endpoint = isFirstMessage ? "/query" : "/continue";

      const payload: any = {
        question: currentInput,
        user_id: user?.id,
        data_source_id: dataSourceId,
      };

      if (!isFirstMessage) {
        payload.session_id = session.id;
      }

      const response = await fetch(process.env.NEXT_PUBLIC_BACKEND_URL + endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.statusText}`);
      }

      const data = await response.json();

      // Update session ID if new
      if (data.session_id && isFirstMessage) {
        setSession((prev: any) => ({ ...prev, id: data.session_id }));
      }

      // Handle clarification needed
      if (data.status === "need_clarification") {
        setClarification({
          status: "need_clarification",
          question: data.question,
          all_questions: data.all_questions || [],
          session_id: data.session_id,
        });
      } 
      // Handle success
      else if (data.status === "completed") {
        setMessages((prev) => [...prev, { role: "assistant", content: data.answer || "" }]);
        
        if (data.insights) {
          setMessages((prev) => [...prev, { role: "insight", content: data.insights }]);
        }
      }
    } catch (err: any) {
      setError(err.message);
      // Remove the optimistic user message on error
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  };

  // Handle clarification response
  const handleClarification = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!clarificationInput.trim() || !clarification) return;

    const currentInput = clarificationInput;
    setClarificationInput("");
    setLoading(true);
    setError(null);

    setMessages((prev) => [...prev, { role: "user", content: currentInput }]);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/clarify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: clarification.session_id,
          answer: currentInput,
        }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.statusText}`);
      }

      const data = await response.json();

      if (data.status === "need_clarification") {
        setClarification({
          status: "need_clarification",
          question: data.question,
          all_questions: data.all_questions || [],
          session_id: data.session_id,
        });
      } 
      else if (data.status === "completed") {
        setMessages((prev) => [...prev, { role: "assistant", content: data.answer || "" }]);
        
        if (data.insights) {
          setMessages((prev) => [...prev, { role: "insight", content: data.insights }]);
        }
        
        setClarification(null);
      }
    } catch (err: any) {
      setError(err.message);
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  };

  const handleCloseChat = async () => {
    await saveSession();
    router.push("/dashboard");
  };

  const handleBackButton = () => {
    // Just navigate back without saving
    router.push("/dashboard");
  };

  const saveSession = async () => {
    if (!session || !dataSourceId || messages.length === 0) {
      console.log("[CHAT] Nothing to save");
      return;
    }

    try {
      const formattedMessages = messages.map(msg => ({
        role: msg.role,
        content: msg.content
      }));

      console.log(`[CHAT] Saving session with ${formattedMessages.length} messages`);

      const response = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/save_session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: session.id,
          user_id: user?.id,
          data_source_id: dataSourceId,
          conversation_history: formattedMessages,
          last_result: session.lastResult,
          last_plan: session.lastPlan,
        }),
      });

      if (response.ok) {
        console.log("[CHAT] Session saved successfully");
      } else {
        console.error("[CHAT] Failed to save session:", await response.text());
      }
    } catch (err) {
      console.error("[CHAT] Error saving session:", err);
    }
  };

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Card className="p-8 max-w-md">
          <CardContent className="text-center">
            <Loader2 className="w-12 h-12 animate-spin text-primary mx-auto mb-4" />
            <p className="text-lg text-muted-foreground">Please sign in to continue</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!dataSourceId || !sessionId) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Card className="p-8 text-center max-w-md">
          <CardContent className="space-y-4">
            <AlertCircle className="w-12 h-12 text-warning mx-auto" />
            <h2 className="text-xl font-semibold text-foreground">No Data Source Selected</h2>
            <p className="text-muted-foreground">Please select a data source from the dashboard</p>
            <Button onClick={() => router.push("/dashboard")} size="lg">
              <ArrowLeft className="w-4 h-4 mr-2" />
              Go to Dashboard
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Header */}
      <motion.div
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="border-b border-border bg-card/50 backdrop-blur-sm sticky top-0 z-40"
      >
        <div className="max-w-5xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleBackButton}
                className="group"
              >
                <ArrowLeft className="w-4 h-4 mr-2 group-hover:-translate-x-1 transition-transform" />
                Back
              </Button>
              <div>
                <h1 className="text-xl font-semibold text-foreground">Chat Session</h1>
                <p className="text-xs text-muted-foreground">
                  Session: {session?.id?.slice(0, 12) || "Loading"}...
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-3">
              <Button
                onClick={handleCloseChat}
                variant="outline"
                size="sm"
              >
                Close & Save
              </Button>
              <UserButton
                afterSignOutUrl="/"
                appearance={{
                  elements: {
                    avatarBox: "w-9 h-9",
                  },
                }}
              />
            </div>
          </div>
        </div>
      </motion.div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto py-8">
        <div className="max-w-4xl mx-auto px-4 space-y-6">
          {loading && messages.length === 0 && (
            <div className="text-center py-12">
              <Card className="max-w-md mx-auto p-8">
                <CardContent className="flex flex-col items-center space-y-4">
                  <Loader2 className="w-12 h-12 text-primary animate-spin" />
                  <p className="text-muted-foreground">Loading conversation...</p>
                </CardContent>
              </Card>
            </div>
          )}

          <AnimatePresence>
            {!loading && messages.length === 0 && !clarification && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="text-center py-12"
              >
                <Card className="max-w-md mx-auto p-8 border-dashed border-2">
                  <CardContent className="space-y-4">
                    <div className="w-16 h-16 bg-gradient-to-br from-primary to-accent rounded-full flex items-center justify-center mx-auto">
                      <Bot className="w-8 h-8 text-white" />
                    </div>
                    <h3 className="text-xl font-semibold text-foreground">
                      Start Your Conversation
                    </h3>
                    <p className="text-muted-foreground">
                      Ask any question about your data in plain English
                    </p>
                  </CardContent>
                </Card>
              </motion.div>
            )}

            {messages.map((msg, idx) => (
              <motion.div
                key={idx}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ delay: idx * 0.05 }}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"} items-start gap-3`}
              >
                {msg.role !== "user" && (
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center flex-shrink-0 mt-1">
                    {msg.role === "insight" ? (
                      <Lightbulb className="w-4 h-4 text-white" />
                    ) : (
                      <Bot className="w-4 h-4 text-white" />
                    )}
                  </div>
                )}

                <div
                  className={`max-w-2xl ${
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground rounded-2xl rounded-br-sm shadow-lg"
                      : msg.role === "insight"
                      ? "bg-accent/20 text-foreground rounded-2xl rounded-bl-sm border border-accent/30"
                      : "bg-card border border-border rounded-2xl rounded-bl-sm shadow-sm"
                  } px-5 py-3.5`}
                >
                  {msg.role === "insight" && (
                    <div className="flex items-center space-x-2 mb-2">
                      <span className="font-semibold text-accent text-sm">AI Insight</span>
                    </div>
                  )}
                  <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                </div>

                {msg.role === "user" && (
                  <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center flex-shrink-0 mt-1">
                    <UserIcon className="w-4 h-4 text-secondary-foreground" />
                  </div>
                )}
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Clarification UI */}
          <AnimatePresence>
            {clarification && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
              >
                <Card className="border-warning/50 bg-warning/5">
                  <CardContent className="pt-6">
                    <div className="flex items-start space-x-3 mb-4">
                      <AlertCircle className="w-6 h-6 text-warning flex-shrink-0 mt-1" />
                      <div className="flex-1">
                        <h3 className="font-semibold text-foreground mb-2">
                          Clarification Needed
                        </h3>
                        <p className="text-muted-foreground mb-4">{clarification.question}</p>

                        {clarification.all_questions.length > 0 && (
                          <div className="space-y-2 mb-4">
                            <p className="text-sm font-medium text-foreground">Quick answers:</p>
                            {clarification.all_questions.map((q, idx) => (
                              <button
                                key={idx}
                                onClick={() => setClarificationInput(q)}
                                className="block w-full text-left px-4 py-3 bg-background border-2 border-border rounded-lg hover:border-primary hover:bg-muted/50 text-sm text-foreground transition-all duration-200 hover:shadow-md"
                              >
                                {q}
                              </button>
                            ))}
                          </div>
                        )}

                        <form onSubmit={handleClarification} className="flex gap-2">
                          <Input
                            value={clarificationInput}
                            onChange={(e) => setClarificationInput(e.target.value)}
                            placeholder="Type your answer..."
                            className="flex-1"
                          />
                          <Button
                            type="submit"
                            disabled={loading || !clarificationInput.trim()}
                          >
                            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                          </Button>
                        </form>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Typing Indicator */}
          {loading && !clarification && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex justify-start items-start gap-3"
            >
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center flex-shrink-0">
                <Bot className="w-4 h-4 text-white" />
              </div>
              <div className="bg-card border border-border rounded-2xl rounded-bl-sm shadow-sm px-5 py-3.5">
                <div className="flex space-x-2">
                  <div className="w-2 h-2 bg-muted-foreground/60 rounded-full animate-bounce" style={{ animationDelay: "0ms" }}></div>
                  <div className="w-2 h-2 bg-muted-foreground/60 rounded-full animate-bounce" style={{ animationDelay: "150ms" }}></div>
                  <div className="w-2 h-2 bg-muted-foreground/60 rounded-full animate-bounce" style={{ animationDelay: "300ms" }}></div>
                </div>
              </div>
            </motion.div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area */}
      {!clarification && (
        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="border-t border-border bg-card/50 backdrop-blur-sm sticky bottom-0"
        >
          <div className="max-w-4xl mx-auto px-4 py-6">
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="mb-4"
              >
                <Card className="border-error/50 bg-error/10">
                  <CardContent className="pt-4 pb-4">
                    <div className="flex items-center space-x-2">
                      <AlertCircle className="w-5 h-5 text-error" />
                      <p className="text-sm text-error flex-1">{error}</p>
                      <button
                        onClick={() => setError(null)}
                        className="text-error hover:text-error/80"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )}

            <form onSubmit={handleSendMessage} className="flex gap-3">
              <Input
                value={userInput}
                onChange={(e) => setUserInput(e.target.value)}
                placeholder="Ask a question about your data..."
                disabled={loading}
                className="flex-1 h-14 text-base"
              />
              <Button
                type="submit"
                disabled={loading || !userInput.trim()}
                size="lg"
                className="px-8"
              >
                {loading ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <>
                    <Send className="w-5 h-5 mr-2" />
                    Send
                  </>
                )}
              </Button>
            </form>
          </div>
        </motion.div>
      )}
    </div>
  );
}