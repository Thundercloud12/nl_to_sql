"use client";

import { useState, useRef } from "react";
import { useUser } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Upload, 
  FileSpreadsheet, 
  CheckCircle, 
  AlertCircle, 
  Loader2, 
  X, 
  ArrowLeft,
  Terminal,
  ShieldCheck,
  Zap
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useServerHealth } from "@/hooks/useServerHealth";

export default function UploadPage() {
  const { user } = useUser();
  const router = useRouter();
  const { isHealthy, isChecking } = useServerHealth();
  const [files, setFiles] = useState<FileList | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null); // Add this ref

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) setFiles(e.target.files);
    setError(null);
    setResult(null);
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(e.type === "dragenter" || e.type === "dragover");
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files?.length > 0) {
      setFiles(e.dataTransfer.files);
      setError(null);
      setResult(null);
    }
  };

  const handleUpload = async () => {
    if (!files || !user?.id) return;
    setUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      for (let i = 0; i < files.length; i++) formData.append("files", files[i]);
      formData.append("user_id", user.id);

      const response = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/upload_and_process`, {
        method: "POST",
        body: formData,
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Upload failed");
      setResult(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleSelectFiles = () => {
    fileInputRef.current?.click(); // Trigger file input
  };

  return (
    <div className="min-h-screen bg-background text-foreground dark:bg-[#0D0E12] dark:text-white pt-24 pb-12 px-4 sm:px-6 lg:px-8 relative overflow-hidden">
      {/* Health Check Loading State */}
      {isChecking && (
        <div className="fixed inset-0 flex flex-col items-center justify-center bg-background/95 dark:bg-[#0D0E12]/95 backdrop-blur-md z-50">
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="text-center"
          >
            <div className="w-16 h-16 bg-muted dark:bg-zinc-900 rounded-2xl flex items-center justify-center mx-auto mb-6 border border-primary/30 dark:border-[#00e599]/30 shadow-[0_0_30px_-10px_rgba(0,113,227,0.3)] dark:shadow-[0_0_30px_-10px_rgba(0,229,153,0.3)]">
              <Loader2 className="w-8 h-8 text-primary dark:text-[#00e599] animate-spin" />
            </div>
            <h2 className="text-2xl font-bold text-foreground mb-2">Warming up backend...</h2>
            <p className="text-zinc-500 max-w-sm mx-auto mb-6">
              Initializing server connection. This may take a moment.
            </p>
            <div className="flex gap-2 justify-center">
              <div className="w-2 h-2 bg-primary dark:bg-[#00e599] rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
              <div className="w-2 h-2 bg-primary dark:bg-[#00e599] rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
              <div className="w-2 h-2 bg-primary dark:bg-[#00e599] rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
          </motion.div>
        </div>
      )}

      {/* Page Content - Hidden while checking */}
      {!isChecking && (
        <>
      {/* Background Decor */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-[500px] bg-[#00e599]/5 blur-[120px] pointer-events-none" />

      <div className="max-w-3xl mx-auto relative z-10">
        {/* Navigation */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mb-10">
          <Button
            variant="ghost"
            onClick={() => router.push("/dashboard")}
            className="text-muted-foreground hover:text-primary dark:hover:text-[#00e599] hover:bg-primary/5 dark:hover:bg-[#00e599]/5 transition-all mb-6 px-0"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back to Dashboard
          </Button>
          <h1 className="text-4xl font-bold tracking-tight mb-2">Ingest Data</h1>
          <p className="text-zinc-500 font-mono text-sm tracking-widest uppercase">
            Upload .CSV or .XLSX for AI training
          </p>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <Card className="bg-card dark:bg-zinc-900/50 border-border dark:border-white/5 backdrop-blur-xl overflow-hidden shadow-2xl">
            <CardContent className="p-8">
              {/* Dropzone Area */}
              {!result && (
                <div
                  onDragEnter={handleDrag}
                  onDragLeave={handleDrag}
                  onDragOver={handleDrag}
                  onDrop={handleDrop}
                  className={cn(
                    "relative border-2 border-dashed rounded-2xl p-12 text-center transition-all duration-300 group",
                    dragActive 
                      ? "border-primary dark:border-[#00e599] bg-primary/5 dark:bg-[#00e599]/5 scale-[1.02]" 
                      : "border-border/50 dark:border-white/10 hover:border-primary/20 dark:hover:border-white/20 hover:bg-muted/50 dark:hover:bg-white/[0.02]"
                  )}
                >
                  <input
                    ref={fileInputRef} // Add ref
                    type="file"
                    id="file-upload"
                    multiple
                    accept=".xlsx,.xls,.csv"
                    onChange={handleFileChange}
                    className="hidden"
                  />

                  <label htmlFor="file-upload" className="cursor-pointer flex flex-col items-center">
                    <div className={cn(
                      "w-20 h-20 rounded-3xl flex items-center justify-center mb-6 transition-all duration-500 shadow-2xl",
                      dragActive ? "bg-primary dark:bg-[#00e599] text-white dark:text-black scale-110" : "bg-muted text-muted-foreground group-hover:text-foreground group-hover:bg-muted/80"
                    )}>
                      <Upload size={32} />
                    </div>
                    
                    <h3 className="text-xl font-bold mb-2 tracking-tight">
                      {dragActive ? "Drop files now" : "Deploy Data Sources"}
                    </h3>
                    
                    <p className="text-sm text-zinc-500 mb-8 max-w-xs mx-auto">
                      Drag and drop your spreadsheet files here or click to browse local storage.
                    </p>

                    <Button 
                      type="button" 
                      variant="outline" 
                      className="border-white/10 hover:bg-white/5 rounded-full px-8"
                      onClick={handleSelectFiles} // Add onClick
                    >
                      Select Files
                    </Button>
                  </label>
                </div>
              )}

              {/* Files List / Processing State */}
              <AnimatePresence>
                {files && files.length > 0 && !result && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="mt-8 space-y-4"
                  >
                    <div className="flex items-center justify-between border-b border-white/5 pb-4">
                      <h4 className="font-mono text-xs text-zinc-500 uppercase tracking-tighter">Queue ({files.length} files)</h4>
                      {!uploading && (
                        <Button variant="ghost" size="sm" onClick={() => setFiles(null)} className="text-red-400 hover:text-red-300 hover:bg-red-400/10 h-8">
                          <X className="w-3 h-3 mr-2" /> Reset
                        </Button>
                      )}
                    </div>
                    
                    <div className="space-y-3">
                      {Array.from(files).map((file, idx) => (
                        <div key={idx} className="flex items-center justify-between p-4 bg-muted/50 dark:bg-black/40 border border-border dark:border-white/5 rounded-xl group hover:border-primary/20 dark:hover:border-white/10 transition-colors">
                          <div className="flex items-center space-x-4">
                            <div className="w-10 h-10 rounded-lg bg-background dark:bg-zinc-800 flex items-center justify-center text-primary dark:text-[#00e599]">
                              <FileSpreadsheet size={18} />
                            </div>
                            <div>
                              <p className="text-sm font-medium text-foreground dark:text-zinc-200">{file.name}</p>
                              <p className="text-xs text-zinc-500 font-mono">{(file.size / 1024).toFixed(1)} KB</p>
                            </div>
                          </div>
                          {uploading && <Loader2 className="w-4 h-4 text-[#00e599] animate-spin" />}
                        </div>
                      ))}
                    </div>

                    <Button
                      onClick={handleUpload}
                      disabled={uploading}
                      className="w-full h-14 bg-black dark:bg-[#00e599] text-white dark:text-black hover:bg-black/90 dark:hover:bg-[#00e599]/90 font-bold text-lg rounded-xl shadow-sm dark:shadow-[0_0_30px_-10px_#00e599] transition-all disabled:opacity-50"
                    >
                      {uploading ? (
                        <div className="flex items-center gap-3">
                          <Loader2 className="w-5 h-5 animate-spin" />
                          <span>Processing Metadata...</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2">
                          <Zap size={20} />
                          <span>Initialize Analysis</span>
                        </div>
                      )}
                    </Button>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Success Result */}
              {result && (
                <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="space-y-6">
                  <div className="bg-primary/10 dark:bg-[#00e599]/10 border border-primary/20 dark:border-[#00e599]/20 rounded-2xl p-8 text-center">
                    <div className="w-16 h-16 bg-primary dark:bg-[#00e599] rounded-full flex items-center justify-center mx-auto mb-4 text-white dark:text-black shadow-sm dark:shadow-[0_0_40px_-10px_#00e599]">
                      <CheckCircle size={32} />
                    </div>
                    <h2 className="text-2xl font-bold text-foreground mb-2">Ingestion Complete</h2>
                    <p className="text-primary/80 dark:text-[#00e599]/80 text-sm mb-6 font-mono">Source ID: {result.data_source_id}</p>
                    
                    <div className="grid grid-cols-2 gap-4 text-left">
                       <div className="p-4 bg-muted rounded-xl border border-border">
                          <p className="text-[10px] text-muted-foreground uppercase mb-1">Status</p>
                          <p className="text-sm font-bold text-foreground">Schema Validated</p>
                       </div>
                       <div className="p-4 bg-muted rounded-xl border border-border">
                          <p className="text-[10px] text-muted-foreground uppercase mb-1">Tables</p>
                          <p className="text-sm font-bold text-foreground">{Object.keys(result.raw_metadata?.tables || {}).length} detected</p>
                       </div>
                    </div>
                  </div>

                  <div className="flex gap-4">
                    <Button onClick={() => router.push("/dashboard")} className="flex-1 h-12 rounded-full bg-foreground text-background hover:opacity-90 font-bold">
                      Enter Dashboard
                    </Button>
                    <Button onClick={() => {setResult(null); setFiles(null);}} variant="outline" className="flex-1 h-12 rounded-full border-border hover:bg-muted">
                      Upload More
                    </Button>
                  </div>
                </motion.div>
              )}

              {/* Error Handler */}
              {error && (
                <div className="mt-6 p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-start gap-4 text-red-400">
                  <AlertCircle className="w-5 h-5 shrink-0" />
                  <div className="text-sm">
                    <p className="font-bold">Error Protocol Triggered</p>
                    <p className="opacity-80">{error}</p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>

        {/* Footer Documentation */}
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }} className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
           {[
             { icon: ShieldCheck, title: "End-to-End Encryption", desc: "Data is salted and hashed before AI processing." },
             { icon: Terminal, title: "Automated Schema", desc: "Our agent detects columns and datatypes instantly." },
             { icon: Zap, title: "Edge Processing", desc: "Lightning fast ingestion for files up to 100MB." }
           ].map((item, i) => (
             <div key={i} className="space-y-2">
                <div className="flex items-center gap-2 text-primary dark:text-[#00e599]">
                  <item.icon size={16} />
                  <span className="text-[10px] font-bold uppercase tracking-widest">{item.title}</span>
                </div>
                <p className="text-xs text-zinc-500 leading-relaxed">{item.desc}</p>
             </div>
           ))}
        </motion.div>
      </div>
        </>
      )}
    </div>
  );
}
