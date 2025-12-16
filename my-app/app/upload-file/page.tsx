"use client";

import { useState } from "react";
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

export default function UploadPage() {
  const { user } = useUser();
  const router = useRouter();
  const [files, setFiles] = useState<FileList | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);

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

  return (
    <div className="min-h-screen bg-[#0D0E12] text-white pt-24 pb-12 px-4 sm:px-6 lg:px-8 relative overflow-hidden">
      {/* Background Decor */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-[500px] bg-[#00e599]/5 blur-[120px] pointer-events-none" />

      <div className="max-w-3xl mx-auto relative z-10">
        {/* Navigation */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mb-10">
          <Button
            variant="ghost"
            onClick={() => router.push("/dashboard")}
            className="text-zinc-500 hover:text-[#00e599] hover:bg-[#00e599]/5 transition-all mb-6 px-0"
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
          <Card className="bg-zinc-900/50 border-white/5 backdrop-blur-xl overflow-hidden shadow-2xl">
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
                      ? "border-[#00e599] bg-[#00e599]/5 scale-[1.02]" 
                      : "border-white/10 hover:border-white/20 hover:bg-white/[0.02]"
                  )}
                >
                  <input
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
                      dragActive ? "bg-[#00e599] text-black scale-110" : "bg-zinc-800 text-zinc-400 group-hover:text-white group-hover:bg-zinc-700"
                    )}>
                      <Upload size={32} />
                    </div>
                    
                    <h3 className="text-xl font-bold mb-2 tracking-tight">
                      {dragActive ? "Drop files now" : "Deploy Data Sources"}
                    </h3>
                    
                    <p className="text-sm text-zinc-500 mb-8 max-w-xs mx-auto">
                      Drag and drop your spreadsheet files here or click to browse local storage.
                    </p>

                    <Button type="button" variant="outline" className="border-white/10 hover:bg-white/5 rounded-full px-8">
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
                        <div key={idx} className="flex items-center justify-between p-4 bg-black/40 border border-white/5 rounded-xl group hover:border-white/10 transition-colors">
                          <div className="flex items-center space-x-4">
                            <div className="w-10 h-10 rounded-lg bg-zinc-800 flex items-center justify-center text-[#00e599]">
                              <FileSpreadsheet size={18} />
                            </div>
                            <div>
                              <p className="text-sm font-medium text-zinc-200">{file.name}</p>
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
                      className="w-full h-14 bg-[#00e599] text-black hover:bg-[#00e599]/90 font-bold text-lg rounded-xl shadow-[0_0_30px_-10px_#00e599] transition-all disabled:opacity-50"
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
                  <div className="bg-[#00e599]/10 border border-[#00e599]/20 rounded-2xl p-8 text-center">
                    <div className="w-16 h-16 bg-[#00e599] rounded-full flex items-center justify-center mx-auto mb-4 text-black shadow-[0_0_40px_-10px_#00e599]">
                      <CheckCircle size={32} />
                    </div>
                    <h2 className="text-2xl font-bold text-white mb-2">Ingestion Complete</h2>
                    <p className="text-[#00e599]/80 text-sm mb-6 font-mono">Source ID: {result.data_source_id}</p>
                    
                    <div className="grid grid-cols-2 gap-4 text-left">
                       <div className="p-4 bg-black/40 rounded-xl border border-[#00e599]/10">
                          <p className="text-[10px] text-zinc-500 uppercase mb-1">Status</p>
                          <p className="text-sm font-bold text-white">Schema Validated</p>
                       </div>
                       <div className="p-4 bg-black/40 rounded-xl border border-[#00e599]/10">
                          <p className="text-[10px] text-zinc-500 uppercase mb-1">Tables</p>
                          <p className="text-sm font-bold text-white">{Object.keys(result.raw_metadata?.tables || {}).length} detected</p>
                       </div>
                    </div>
                  </div>

                  <div className="flex gap-4">
                    <Button onClick={() => router.push("/dashboard")} className="flex-1 h-12 rounded-full bg-white text-black hover:bg-zinc-200 font-bold">
                      Enter Dashboard
                    </Button>
                    <Button onClick={() => {setResult(null); setFiles(null);}} variant="outline" className="flex-1 h-12 rounded-full border-white/10 hover:bg-white/5">
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
                <div className="flex items-center gap-2 text-[#00e599]">
                  <item.icon size={16} />
                  <span className="text-[10px] font-bold uppercase tracking-widest">{item.title}</span>
                </div>
                <p className="text-xs text-zinc-500 leading-relaxed">{item.desc}</p>
             </div>
           ))}
        </motion.div>
      </div>
    </div>
  );
}
