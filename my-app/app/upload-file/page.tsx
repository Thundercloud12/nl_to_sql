"use client";

import { useState } from "react";
import { useUser } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Upload, FileSpreadsheet, CheckCircle, AlertCircle, Loader2, X, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export default function UploadPage() {
  const { user } = useUser();
  const router = useRouter();
  const [files, setFiles] = useState<FileList | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFiles(e.target.files);
    setError(null);
    setResult(null);
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setFiles(e.dataTransfer.files);
      setError(null);
      setResult(null);
    }
  };

  const handleUpload = async () => {
    if (!files || files.length === 0) {
      setError("Please select at least one file");
      return;
    }

    if (!user?.id) {
      setError("User not authenticated");
      return;
    }

    setUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      
      // Add files
      for (let i = 0; i < files.length; i++) {
        formData.append("files", files[i]);
      }
      
      // Add user_id
      formData.append("user_id", user.id);

      const response = await fetch("http://localhost:8000/upload_and_process", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Upload failed");
      }

      setResult(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const clearFiles = () => {
    setFiles(null);
    setResult(null);
    setError(null);
  };

  return (
    <div className="min-h-screen py-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push("/dashboard")}
            className="group mb-4"
          >
            <ArrowLeft className="w-4 h-4 mr-2 group-hover:-translate-x-1 transition-transform" />
            Back to Dashboard
          </Button>
          
          <h1 className="text-4xl font-bold text-foreground mb-2">
            Upload Data Files
          </h1>
          <p className="text-lg text-muted-foreground">
            Upload your Excel or CSV files to start analyzing
          </p>
        </motion.div>

        {/* Upload Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <Card>
            <CardContent className="pt-6">
              {/* Drag and Drop Area */}
              <div
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                className={`relative border-2 border-dashed rounded-xl p-12 text-center transition-all duration-200 ${
                  dragActive
                    ? "border-primary bg-primary/5 scale-105"
                    : "border-border hover:border-primary/50 hover:bg-muted/20"
                }`}
              >
                <input
                  type="file"
                  id="file-upload"
                  multiple
                  accept=".xlsx,.xls,.csv"
                  onChange={handleFileChange}
                  className="hidden"
                />

                <label
                  htmlFor="file-upload"
                  className="cursor-pointer flex flex-col items-center"
                >
                  <div className={`w-20 h-20 rounded-full flex items-center justify-center mb-4 transition-colors ${
                    dragActive ? "bg-primary" : "bg-muted"
                  }`}>
                    <Upload className={`w-10 h-10 ${dragActive ? "text-white" : "text-muted-foreground"}`} />
                  </div>
                  
                  <h3 className="text-xl font-semibold text-foreground mb-2">
                    {dragActive ? "Drop files here" : "Choose files or drag them here"}
                  </h3>
                  
                  <p className="text-sm text-muted-foreground mb-4">
                    Supported formats: .xlsx, .xls, .csv
                  </p>

                  <Button type="button" variant="outline" size="lg">
                    Browse Files
                  </Button>
                </label>
              </div>

              {/* Selected Files */}
              {files && files.length > 0 && !result && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-6"
                >
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="font-medium text-foreground">Selected Files ({files.length})</h4>
                    <Button variant="ghost" size="sm" onClick={clearFiles}>
                      <X className="w-4 h-4 mr-1" />
                      Clear
                    </Button>
                  </div>
                  
                  <div className="space-y-2">
                    {Array.from(files).map((file, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between p-3 bg-muted rounded-lg"
                      >
                        <div className="flex items-center space-x-3">
                          <FileSpreadsheet className="w-5 h-5 text-primary" />
                          <div>
                            <p className="text-sm font-medium text-foreground">{file.name}</p>
                            <p className="text-xs text-muted-foreground">
                              {(file.size / 1024).toFixed(2)} KB
                            </p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </motion.div>
              )}

              {/* Upload Button */}
              {files && files.length > 0 && !result && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-6"
                >
                  <Button
                    onClick={handleUpload}
                    disabled={uploading}
                    size="lg"
                    className="w-full"
                  >
                    {uploading ? (
                      <>
                        <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                        Uploading & Processing...
                      </>
                    ) : (
                      <>
                        <Upload className="w-5 h-5 mr-2" />
                        Upload Files
                      </>
                    )}
                  </Button>
                </motion.div>
              )}

              {/* Error Message */}
              {error && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="mt-6"
                >
                  <Card className="border-error/50 bg-error/10">
                    <CardContent className="pt-6">
                      <div className="flex items-start space-x-3">
                        <AlertCircle className="w-5 h-5 text-error flex-shrink-0 mt-0.5" />
                        <div className="flex-1">
                          <h4 className="font-medium text-error mb-1">Upload Failed</h4>
                          <p className="text-sm text-error/80">{error}</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              )}

              {/* Success Message */}
              {result && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="mt-6"
                >
                  <Card className="border-success/50 bg-success/10">
                    <CardContent className="pt-6">
                      <div className="flex items-start space-x-3 mb-4">
                        <CheckCircle className="w-6 h-6 text-success flex-shrink-0" />
                        <div className="flex-1">
                          <h4 className="font-semibold text-success text-lg mb-1">
                            Upload Successful!
                          </h4>
                          <p className="text-sm text-success/80 mb-4">
                            Your data has been processed and is ready to use
                          </p>
                          
                          <div className="bg-background/50 rounded-lg p-4 space-y-2 text-sm">
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">Data Source ID:</span>
                              <code className="text-xs bg-muted px-2 py-1 rounded font-mono text-foreground">
                                {result.data_source_id?.slice(0, 16)}...
                              </code>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">Tables Processed:</span>
                              <span className="font-medium text-foreground">
                                {Object.keys(result.raw_metadata?.tables || {}).length}
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="flex gap-3">
                        <Button
                          onClick={() => router.push("/dashboard")}
                          className="flex-1"
                        >
                          Go to Dashboard
                        </Button>
                        <Button
                          onClick={clearFiles}
                          variant="outline"
                          className="flex-1"
                        >
                          Upload More
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              )}
            </CardContent>
          </Card>
        </motion.div>

        {/* Info Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="mt-8"
        >
          <Card className="bg-muted/30">
            <CardContent className="pt-6">
              <h3 className="font-semibold text-foreground mb-3">How it works</h3>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li className="flex items-start">
                  <span className="mr-2">1.</span>
                  <span>Upload your Excel or CSV files</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">2.</span>
                  <span>Our AI analyzes your data structure and creates a schema</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">3.</span>
                  <span>Start asking questions in natural language</span>
                </li>
              </ul>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}