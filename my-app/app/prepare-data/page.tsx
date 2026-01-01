"use client";

import { useState, useRef, useEffect } from "react";
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
  Sparkles,
  Download,
  TrendingUp,
  Target,
  ChevronRight,
  Info,
  Brain,
  Zap,
  Shield,
  Activity,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useServerHealth } from "@/hooks/useServerHealth";

// Types
interface IntentOption {
  id: string;
  name: string;
  description: string;
}

interface Profile {
  structure: string;
  columns: Record<string, any>;
  quality_issues: Array<{
    severity: string;
    category: string;
    message: string;
  }>;
  recommended_mode: string;
  row_count: number;
  [key: string]: any; // For additional fields
}

interface ExpertPlan {
  expert_name: string;
  score: number;
  confidence_score: number;
  operations: Array<{
    operation_type?: string;    // Primary field
    id?: string;                // Fallback for backwards compatibility
    column: string;
    reason: string;
    expected_impact: any;
  }>;
  pros: string[];
  cons: string[];
  estimated_row_loss: number;
  estimated_variance_change: number;
  risk_flags: string[];
  overall_justification: string;
}

interface CleaningResult {
  cleaned_file_name: string;
  download_url: string;
  decision_log: any;
  actual_stats: {
    deltas: {
      row_loss: number;
      missing_reduction: number;
    };
  };
  expert_plan_used: {
    name: string;
    score: number;
    operations_applied: number;
  };
}

type Step = "upload" | "profile" | "intent" | "plans" | "clean" | "complete";

export default function PrepareDataPage() {
  const { user } = useUser();
  const router = useRouter();
  const { isHealthy, isChecking } = useServerHealth();
  const fileInputRef = useRef<HTMLInputElement>(null);

  console.log("[PREPARE-DATA] 🚀 Component mounted/rendered");
  console.log("[PREPARE-DATA] User:", user?.id);
  console.log("[PREPARE-DATA] Backend URL:", process.env.NEXT_PUBLIC_BACKEND_URL);
  console.log("[PREPARE-DATA] Server health:", { isHealthy, isChecking });

  // State
  const [step, setStep] = useState<Step>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Data state
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [intentOptions, setIntentOptions] = useState<IntentOption[]>([]);
  const [selectedIntent, setSelectedIntent] = useState<string | null>(null);
  const [expertPlans, setExpertPlans] = useState<ExpertPlan[]>([]);
  const [recommendedPlan, setRecommendedPlan] = useState<string | null>(null);
  const [selectedExpert, setSelectedExpert] = useState<string | null>(null);
  const [cleaningResult, setCleaningResult] = useState<CleaningResult | null>(null);

  // Log step changes
  useEffect(() => {
    console.log("[PREPARE-DATA] 📍 Step changed to:", step);
  }, [step]);

  // Log when data states change
  useEffect(() => {
    if (profile) {
      console.log("[PREPARE-DATA] 📊 Profile state updated:", {
        rows: profile.row_count,
        columns: Object.keys(profile.columns).length,
        structure: profile.structure,
        recommended_mode: profile.recommended_mode,
        issues: profile.quality_issues?.length,
      });
    }
  }, [profile]);

  useEffect(() => {
    if (expertPlans.length > 0) {
      console.log("[PREPARE-DATA] 🧠 Expert plans state updated:", {
        count: expertPlans.length,
        plans: expertPlans.map(p => ({ name: p.expert_name, score: p.score })),
      });
    }
  }, [expertPlans]);

  useEffect(() => {
    if (cleaningResult) {
      console.log("[PREPARE-DATA] ✨ Cleaning result state updated:", {
        file: cleaningResult.cleaned_file_name,
        rowsRemoved: cleaningResult.actual_stats?.deltas?.row_loss,
        missingFixed: cleaningResult.actual_stats?.deltas?.missing_reduction,
      });
    }
  }, [cleaningResult]);

  // Handlers
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
      const droppedFile = e.dataTransfer.files[0];
      console.log("[PREPARE-DATA] 🎯 File dropped:", {
        name: droppedFile.name,
        size: droppedFile.size,
        type: droppedFile.type,
        lastModified: new Date(droppedFile.lastModified).toISOString(),
      });
      setFile(droppedFile);
      setError(null);
    } else {
      console.log("[PREPARE-DATA] ⚠️ Drop event with no files");
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) {
      const selectedFile = e.target.files[0];
      console.log("[PREPARE-DATA] 📁 File selected:", {
        name: selectedFile.name,
        size: selectedFile.size,
        type: selectedFile.type,
        lastModified: new Date(selectedFile.lastModified).toISOString(),
      });
      setFile(selectedFile);
      setError(null);
    }
  };

  const handleUploadAndProfile = async () => {
    if (!file) return;
    console.log("[PREPARE-DATA] 📤 Starting upload and profile...");
    console.log("[PREPARE-DATA] File details:", {
      name: file.name,
      size: file.size,
      type: file.type,
    });
    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      console.log("[PREPARE-DATA] 🌐 Sending request to:", `${process.env.NEXT_PUBLIC_BACKEND_URL}/prepare_data/profile`);
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_BACKEND_URL}/prepare_data/profile`,
        {
          method: "POST",
          body: formData,
        }
      );

      console.log("[PREPARE-DATA] 📡 Response status:", response.status, response.statusText);
      if (!response.ok) throw new Error("Failed to profile data");

      const data = await response.json();
      console.log("[PREPARE-DATA] ✅ Received profile data:", data);
      console.log("[PREPARE-DATA] Session ID:", data.session_id);
      console.log("[PREPARE-DATA] File name:", data.file_name);
      console.log("[PREPARE-DATA] Profile object keys:", Object.keys(data.profile || {}));
      console.log("[PREPARE-DATA] Profile structure:", data.profile?.structure);
      console.log("[PREPARE-DATA] Profile recommended_mode:", data.profile?.recommended_mode);
      console.log("[PREPARE-DATA] Profile summary:", {
        rows: data.profile?.row_count,
        columns: data.profile?.columns ? Object.keys(data.profile.columns).length : 0,
        structure: data.profile?.structure,
        recommended_mode: data.profile?.recommended_mode,
        issues: data.profile?.quality_issues?.length,
      });
      console.log("[PREPARE-DATA] Intent options:", data.intent_options);
      
      setSessionId(data.session_id);
      setProfile(data.profile);
      setIntentOptions(data.intent_options);
      setStep("intent");
    } catch (err: any) {
      console.error("[PREPARE-DATA] ❌ Error during upload/profile:", err);
      setError(err.message || "Failed to upload and profile file");
    } finally {
      setLoading(false);
    }
  };

  const handleGeneratePlans = async () => {
    if (!sessionId || !selectedIntent) {
      console.warn("[PREPARE-DATA] ⚠️ Cannot generate plans - missing sessionId or intent");
      return;
    }
    console.log("[PREPARE-DATA] 🧠 Generating expert plans...");
    console.log("[PREPARE-DATA] Request params:", {
      session_id: sessionId,
      intent: selectedIntent,
    });
    setLoading(true);
    setError(null);

    try {
      const requestBody = {
        session_id: sessionId,
        intent: selectedIntent,
      };
      console.log("[PREPARE-DATA] 🌐 Sending request to:", `${process.env.NEXT_PUBLIC_BACKEND_URL}/prepare_data/generate_plans`);
      console.log("[PREPARE-DATA] Request body:", requestBody);
      
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_BACKEND_URL}/prepare_data/generate_plans`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(requestBody),
        }
      );

      console.log("[PREPARE-DATA] 📡 Response status:", response.status, response.statusText);
      if (!response.ok) throw new Error("Failed to generate expert plans");

      const data = await response.json();
      console.log("[PREPARE-DATA] ✅ Received expert plans data:", data);
      console.log("[PREPARE-DATA] Number of plans:", data.expert_plans?.length);
      console.log("[PREPARE-DATA] Recommended plan:", data.recommended_plan);
      console.log("[PREPARE-DATA] Intent context:", data.intent_context);
      console.log("[PREPARE-DATA] Arbiter reasoning:", data.arbiter_reasoning);
      data.expert_plans?.forEach((plan: any, idx: number) => {
        console.log(`[PREPARE-DATA] Plan ${idx + 1}:`, {
          name: plan.expert_name,
          score: plan.score,
          confidence_score: plan.confidence_score,
          operations: plan.operations?.length,
          pros: plan.pros?.length,
          cons: plan.cons?.length,
          estimated_row_loss: plan.estimated_row_loss,
          estimated_variance_change: plan.estimated_variance_change,
          risk_flags: plan.risk_flags?.length,
        });
      });
      
      setExpertPlans(data.expert_plans);
      setRecommendedPlan(data.recommended_plan);
      setSelectedExpert(data.recommended_plan); // Auto-select recommended
      setStep("plans");
    } catch (err: any) {
      console.error("[PREPARE-DATA] ❌ Error generating plans:", err);
      setError(err.message || "Failed to generate plans");
    } finally {
      setLoading(false);
    }
  };

  const handleCleanData = async () => {
    if (!sessionId || !selectedExpert) {
      console.warn("[PREPARE-DATA] ⚠️ Cannot clean data - missing sessionId or selectedExpert");
      return;
    }
    console.log("[PREPARE-DATA] 🧹 Starting data cleaning...");
    console.log("[PREPARE-DATA] Request params:", {
      session_id: sessionId,
      selected_expert: selectedExpert,
    });
    setLoading(true);
    setError(null);

    try {
      const requestBody = {
        session_id: sessionId,
        selected_expert: selectedExpert,
      };
      console.log("[PREPARE-DATA] 🌐 Sending request to:", `${process.env.NEXT_PUBLIC_BACKEND_URL}/prepare_data/clean`);
      console.log("[PREPARE-DATA] Request body:", requestBody);
      
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_BACKEND_URL}/prepare_data/clean`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(requestBody),
        }
      );

      console.log("[PREPARE-DATA] 📡 Response status:", response.status, response.statusText);
      if (!response.ok) throw new Error("Failed to clean data");

      const data = await response.json();
      console.log("[PREPARE-DATA] ✅ Received cleaning results:", data);
      console.log("[PREPARE-DATA] Cleaned file name:", data.cleaned_file_name);
      console.log("[PREPARE-DATA] Download URL:", data.download_url);
      console.log("[PREPARE-DATA] Actual stats:", data.actual_stats);
      console.log("[PREPARE-DATA] Expert plan used:", data.expert_plan_used);
      console.log("[PREPARE-DATA] Decision log:", data.decision_log);
      
      setCleaningResult(data);
      setStep("complete");
    } catch (err: any) {
      console.error("[PREPARE-DATA] ❌ Error cleaning data:", err);
      setError(err.message || "Failed to clean data");
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = () => {
    if (!cleaningResult || !sessionId) {
      console.warn("[PREPARE-DATA] ⚠️ Cannot download - missing cleaningResult or sessionId");
      return;
    }
    const downloadUrl = `${process.env.NEXT_PUBLIC_BACKEND_URL}/prepare_data/download/${sessionId}`;
    console.log("[PREPARE-DATA] 📥 Downloading cleaned file from:", downloadUrl);
    console.log("[PREPARE-DATA] File name:", cleaningResult.cleaned_file_name);
    window.open(downloadUrl, "_blank");
  };

  const handleReset = () => {
    console.log("[PREPARE-DATA] 🔄 Resetting workflow to start");
    setStep("upload");
    setFile(null);
    setSessionId(null);
    setProfile(null);
    setIntentOptions([]);
    setSelectedIntent(null);
    setExpertPlans([]);
    setRecommendedPlan(null);
    setSelectedExpert(null);
    setCleaningResult(null);
    setError(null);
    console.log("[PREPARE-DATA] ✅ Workflow reset complete");
  };

  // Render functions
  const renderUploadStep = () => (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="max-w-2xl mx-auto"
    >
      <Card className="border-2 border-dashed border-primary/20 bg-background/50 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-2xl">
            <Sparkles className="w-6 h-6 text-primary" />
            Prepare Your Data
          </CardTitle>
          <CardDescription>
            Upload your dataset to get AI-powered cleaning recommendations tailored to your use case
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div
            className={cn(
              "relative border-2 border-dashed rounded-lg p-12 text-center transition-all cursor-pointer",
              dragActive
                ? "border-primary bg-primary/5 scale-[1.02]"
                : "border-muted-foreground/25 hover:border-primary/50 hover:bg-accent/50",
              file && "border-primary bg-primary/5"
            )}
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx,.xls"
              className="hidden"
              onChange={handleFileChange}
            />

            {file ? (
              <div className="flex flex-col items-center gap-4">
                <div className="relative">
                  <FileSpreadsheet className="w-16 h-16 text-primary" />
                  <CheckCircle className="w-6 h-6 text-green-500 absolute -top-1 -right-1" />
                </div>
                <div>
                  <p className="font-semibold text-lg">{file.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    setFile(null);
                  }}
                >
                  <X className="w-4 h-4 mr-2" />
                  Remove
                </Button>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-4">
                <Upload className="w-16 h-16 text-muted-foreground" />
                <div>
                  <p className="font-semibold text-lg">
                    Drop your file here or click to browse
                  </p>
                  <p className="text-sm text-muted-foreground mt-2">
                    Supported formats: CSV, Excel (.xlsx, .xls)
                  </p>
                </div>
              </div>
            )}
          </div>

          {error && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="mt-4 p-4 rounded-lg bg-destructive/10 border border-destructive/20 flex items-start gap-3"
            >
              <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />
              <p className="text-sm text-destructive">{error}</p>
            </motion.div>
          )}

          <div className="mt-6 flex gap-3">
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => router.push("/dashboard")}
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Dashboard
            </Button>
            <Button
              className="flex-1"
              onClick={handleUploadAndProfile}
              disabled={!file || loading || !isHealthy}
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Analyzing...
                </>
              ) : (
                <>
                  <Activity className="w-4 h-4 mr-2" />
                  Analyze Dataset
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );

  const renderIntentStep = () => (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="max-w-4xl mx-auto"
    >
      <Card className="bg-background/50 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-2xl">
            <Target className="w-6 h-6 text-primary" />
            Dataset Profile & Intent
          </CardTitle>
          <CardDescription>
            We've analyzed your data. Now tell us what you plan to use it for.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Profile Summary */}
          {profile && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 rounded-lg bg-primary/5 border border-primary/10">
                <p className="text-sm text-muted-foreground">Rows</p>
                <p className="text-2xl font-bold">{profile.row_count.toLocaleString()}</p>
              </div>
              <div className="p-4 rounded-lg bg-primary/5 border border-primary/10">
                <p className="text-sm text-muted-foreground">Columns</p>
                <p className="text-2xl font-bold">{Object.keys(profile.columns).length}</p>
              </div>
              <div className="p-4 rounded-lg bg-primary/5 border border-primary/10">
                <p className="text-sm text-muted-foreground">Issues Found</p>
                <p className="text-2xl font-bold">{profile.quality_issues.length}</p>
              </div>
            </div>
          )}

          {/* Quality Issues */}
          {profile && profile.quality_issues.length > 0 && (
            <div className="space-y-2">
              <h3 className="font-semibold flex items-center gap-2">
                <AlertCircle className="w-4 h-4" />
                Data Quality Issues
              </h3>
              <div className="space-y-2 max-h-40 overflow-y-auto">
                {profile.quality_issues.slice(0, 5).map((issue, idx) => (
                  <div
                    key={idx}
                    className={cn(
                      "p-3 rounded-lg text-sm border",
                      issue.severity === "high"
                        ? "bg-destructive/5 border-destructive/20"
                        : issue.severity === "medium"
                        ? "bg-yellow-500/5 border-yellow-500/20"
                        : "bg-muted border-muted"
                    )}
                  >
                    <span className="font-medium">[{issue.category}]</span> {issue.message}
                  </div>
                ))}
                {profile.quality_issues.length > 5 && (
                  <p className="text-sm text-muted-foreground text-center">
                    + {profile.quality_issues.length - 5} more issues
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Intent Selection */}
          <div className="space-y-3">
            <h3 className="font-semibold flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-primary" />
              What will you use this data for?
            </h3>
            <div className="grid gap-3">
              {intentOptions.map((intent) => (
                <button
                  key={intent.id}
                  onClick={() => {
                    console.log("[PREPARE-DATA] 🎯 Intent selected:", {
                      id: intent.id,
                      name: intent.name,
                      description: intent.description,
                    });
                    setSelectedIntent(intent.id);
                  }}
                  className={cn(
                    "p-4 rounded-lg border-2 text-left transition-all hover:scale-[1.02]",
                    selectedIntent === intent.id
                      ? "border-primary bg-primary/5"
                      : "border-muted hover:border-primary/50"
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      <p className="font-semibold">{intent.name}</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        {intent.description}
                      </p>
                    </div>
                    {selectedIntent === intent.id && (
                      <CheckCircle className="w-5 h-5 text-primary flex-shrink-0" />
                    )}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {error && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="p-4 rounded-lg bg-destructive/10 border border-destructive/20 flex items-start gap-3"
            >
              <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />
              <p className="text-sm text-destructive">{error}</p>
            </motion.div>
          )}

          <div className="flex gap-3">
            <Button variant="outline" onClick={handleReset}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Start Over
            </Button>
            <Button
              className="flex-1"
              onClick={handleGeneratePlans}
              disabled={!selectedIntent || loading}
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Generating Expert Plans...
                </>
              ) : (
                <>
                  <Brain className="w-4 h-4 mr-2" />
                  Get AI Recommendations
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );

  const renderPlansStep = () => {
    const getExpertIcon = (name: string) => {
      if (name.includes("Preservation")) return Shield;
      if (name.includes("Stability")) return Activity;
      if (name.includes("Model")) return Zap;
      return Brain;
    };

    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="max-w-5xl mx-auto"
      >
        <Card className="bg-background/50 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-2xl">
              <Brain className="w-6 h-6 text-primary" />
              Expert Cleaning Recommendations
            </CardTitle>
            <CardDescription>
              Our AI has generated 3 different cleaning strategies. Choose the one that best fits your needs.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {expertPlans.map((plan, idx) => {
              const expertId = `expert_${idx + 1}`;
              const isRecommended = expertId === recommendedPlan;
              const isSelected = expertId === selectedExpert;
              const Icon = getExpertIcon(plan.expert_name);

              return (
                <button
                  key={expertId}
                  onClick={() => {
                    console.log("[PREPARE-DATA] 👨‍🔬 Expert plan selected:", {
                      expertId: expertId,
                      name: plan.expert_name,
                      score: plan.score,
                      operations: plan.operations?.length,
                    });
                    setSelectedExpert(expertId);
                  }}
                  className={cn(
                    "w-full p-5 rounded-lg border-2 text-left transition-all hover:scale-[1.01]",
                    isSelected
                      ? "border-primary bg-primary/5 shadow-lg"
                      : "border-muted hover:border-primary/50"
                  )}
                >
                  <div className="flex items-start gap-4">
                    <div
                      className={cn(
                        "p-3 rounded-lg",
                        isSelected ? "bg-primary/10" : "bg-muted"
                      )}
                    >
                      <Icon className={cn("w-6 h-6", isSelected && "text-primary")} />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <h3 className="font-bold text-lg">{plan.expert_name}</h3>
                        {isRecommended && (
                          <span className="px-2 py-1 text-xs font-semibold bg-primary text-primary-foreground rounded-full">
                            RECOMMENDED
                          </span>
                        )}
                        <span className="ml-auto text-2xl font-bold text-primary">
                          {plan.score}/100
                        </span>
                      </div>

                      {/* Estimated Impact */}
                      <div className="grid grid-cols-2 gap-3 mb-3">
                        <div className="text-sm">
                          <p className="text-muted-foreground">Row Loss</p>
                          <p className="font-semibold">{plan.estimated_row_loss}</p>
                        </div>
                        <div className="text-sm">
                          <p className="text-muted-foreground">Variance Change</p>
                          <p className="font-semibold">{plan.estimated_variance_change}%</p>
                        </div>
                      </div>

                      {/* Pros */}
                      <div className="mb-2">
                        <p className="text-sm font-semibold text-green-600 dark:text-green-400 mb-1">
                          ✓ Advantages:
                        </p>
                        <ul className="text-sm text-muted-foreground space-y-1">
                          {plan.pros.slice(0, 2).map((pro, i) => (
                            <li key={i}>• {pro}</li>
                          ))}
                        </ul>
                      </div>

                      {/* Cons */}
                      <div>
                        <p className="text-sm font-semibold text-orange-600 dark:text-orange-400 mb-1">
                          ⚠ Trade-offs:
                        </p>
                        <ul className="text-sm text-muted-foreground space-y-1">
                          {plan.cons.slice(0, 2).map((con, i) => (
                            <li key={i}>• {con}</li>
                          ))}
                        </ul>
                      </div>

                      <div className="mt-3 pt-3 border-t">
                        <p className="text-xs text-muted-foreground">
                          {plan.operations.length} cleaning operations planned
                        </p>
                      </div>
                    </div>
                  </div>
                </button>
              );
            })}

            {error && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="p-4 rounded-lg bg-destructive/10 border border-destructive/20 flex items-start gap-3"
              >
                <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />
                <p className="text-sm text-destructive">{error}</p>
              </motion.div>
            )}

            <div className="flex gap-3 pt-4">
              <Button variant="outline" onClick={() => setStep("intent")}>
                <ArrowLeft className="w-4 h-4 mr-2" />
                Change Intent
              </Button>
              <Button
                className="flex-1"
                onClick={handleCleanData}
                disabled={!selectedExpert || loading}
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Cleaning Data...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4 mr-2" />
                    Apply Selected Plan
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    );
  };

  const renderCompleteStep = () => (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="max-w-3xl mx-auto"
    >
      <Card className="bg-background/50 backdrop-blur-sm border-2 border-primary/20">
        <CardHeader className="text-center">
          <div className="mx-auto w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center mb-4">
            <CheckCircle className="w-10 h-10 text-primary" />
          </div>
          <CardTitle className="text-2xl">Data Cleaning Complete!</CardTitle>
          <CardDescription>
            Your dataset has been successfully cleaned and is ready to use
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {cleaningResult && (
            <>
              {/* Summary Stats */}
              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 rounded-lg bg-primary/5 border border-primary/10">
                  <p className="text-sm text-muted-foreground">Rows Removed</p>
                  <p className="text-2xl font-bold">
                    {cleaningResult.actual_stats.deltas.row_loss.toLocaleString()}
                  </p>
                </div>
                <div className="p-4 rounded-lg bg-primary/5 border border-primary/10">
                  <p className="text-sm text-muted-foreground">Missing Cells Fixed</p>
                  <p className="text-2xl font-bold">
                    {cleaningResult.actual_stats.deltas.missing_reduction.toLocaleString()}
                  </p>
                </div>
              </div>

              {/* Expert Plan Used */}
              <div className="p-4 rounded-lg bg-muted/50 border">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-semibold flex items-center gap-2">
                    <Brain className="w-4 h-4" />
                    {cleaningResult.expert_plan_used.name}
                  </h3>
                  <span className="text-sm font-semibold text-primary">
                    Score: {cleaningResult.expert_plan_used.score}/100
                  </span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Applied {cleaningResult.expert_plan_used.operations_applied} cleaning operations
                </p>
              </div>

              {/* Download Button */}
              <div className="space-y-3">
                <Button
                  className="w-full"
                  size="lg"
                  onClick={handleDownload}
                >
                  <Download className="w-5 h-5 mr-2" />
                  Download Cleaned Dataset
                </Button>
                <p className="text-xs text-center text-muted-foreground">
                  File: {cleaningResult.cleaned_file_name}
                </p>
              </div>
            </>
          )}

          <div className="flex gap-3">
            <Button variant="outline" className="flex-1" onClick={handleReset}>
              Clean Another File
            </Button>
            <Button variant="outline" className="flex-1" onClick={() => router.push("/dashboard")}>
              Back to Dashboard
            </Button>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );

  // Main render
  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-primary/5">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
            Data Preparation Studio
          </h1>
          <p className="text-muted-foreground mt-2">
            AI-powered data cleaning with expert recommendations
          </p>
        </div>

        {/* Progress Indicator */}
        <div className="mb-8 max-w-4xl mx-auto">
          <div className="flex items-center justify-between">
            {[
              { id: "upload", label: "Upload", icon: Upload },
              { id: "intent", label: "Intent", icon: Target },
              { id: "plans", label: "Plans", icon: Brain },
              { id: "complete", label: "Complete", icon: CheckCircle },
            ].map((s, idx, arr) => {
              const stepOrder = ["upload", "intent", "plans", "complete"];
              const currentIdx = stepOrder.indexOf(step);
              const thisIdx = stepOrder.indexOf(s.id);
              const isActive = thisIdx === currentIdx;
              const isComplete = thisIdx < currentIdx;

              return (
                <div key={s.id} className="flex items-center flex-1">
                  <div className="flex flex-col items-center gap-2 flex-1">
                    <div
                      className={cn(
                        "w-10 h-10 rounded-full border-2 flex items-center justify-center transition-all",
                        isActive
                          ? "border-primary bg-primary text-primary-foreground"
                          : isComplete
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-muted-foreground/20 bg-background text-muted-foreground"
                      )}
                    >
                      <s.icon className="w-5 h-5" />
                    </div>
                    <span
                      className={cn(
                        "text-xs font-medium",
                        isActive || isComplete
                          ? "text-foreground"
                          : "text-muted-foreground"
                      )}
                    >
                      {s.label}
                    </span>
                  </div>
                  {idx < arr.length - 1 && (
                    <div
                      className={cn(
                        "h-[2px] flex-1 mx-2 transition-all",
                        isComplete
                          ? "bg-primary"
                          : "bg-muted-foreground/20"
                      )}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Step Content */}
        <AnimatePresence mode="wait">
          {step === "upload" && renderUploadStep()}
          {step === "intent" && renderIntentStep()}
          {step === "plans" && renderPlansStep()}
          {step === "complete" && renderCompleteStep()}
        </AnimatePresence>

        {/* Server Status */}
        {!isHealthy && !isChecking && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="fixed bottom-4 right-4 p-4 rounded-lg bg-yellow-500/10 border border-yellow-500/20 backdrop-blur-sm"
          >
            <div className="flex items-center gap-2 text-sm">
              <AlertCircle className="w-4 h-4 text-yellow-500" />
              <span>Backend server is not responding</span>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}
