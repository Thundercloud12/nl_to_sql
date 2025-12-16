"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { SignedIn, SignedOut, useUser } from "@clerk/nextjs";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Sparkles, 
  Zap, 
  ArrowRight, 
  MessageSquare, 
  Upload, 
  BarChart3, 
  Terminal,
  Cpu,
  ShieldCheck,
  Command
} from "lucide-react";
import { Button } from "@/components/ui/button";

// --- Components for the Hero Animation ---

const TypewriterText = ({ text, onComplete }: { text: string; onComplete?: () => void }) => {
  const [displayedText, setDisplayedText] = useState("");

  useEffect(() => {
    let index = 0;
    const intervalId = setInterval(() => {
      setDisplayedText(text.slice(0, index + 1));
      index++;
      if (index === text.length) {
        clearInterval(intervalId);
        if (onComplete) setTimeout(onComplete, 500);
      }
    }, 50); // Typing speed
    return () => clearInterval(intervalId);
  }, [text, onComplete]);

  return <span>{displayedText}<span className="animate-pulse">|</span></span>;
};

const BarGraph = () => {
  // Random data for the visual
  const data = [40, 70, 45, 90, 60, 85, 100];
  
  return (
    <div className="flex items-end justify-between h-40 w-full gap-2 px-4 pb-2">
      {data.map((h, i) => (
        <motion.div
          key={i}
          initial={{ height: 0 }}
          animate={{ height: `${h}%` }}
          transition={{ duration: 0.8, delay: i * 0.1, type: "spring" }}
          className="w-full bg-[#00e599] rounded-t-sm opacity-80 hover:opacity-100 transition-opacity"
        >
          <div className="w-full h-full bg-gradient-to-t from-black/50 to-transparent" />
        </motion.div>
      ))}
    </div>
  );
};

// --- Main Page Component ---

export default function LandingPage() {
  const { user, isLoaded } = useUser();
  const router = useRouter();
  
  // Animation State Sequence
  const [animationStep, setAnimationStep] = useState<"idle" | "typing" | "thinking" | "result">("typing");

  useEffect(() => {
    if (isLoaded && user) {
      router.push("/dashboard");
    }
  }, [isLoaded, user, router]);

  // Loop the animation
  useEffect(() => {
    if (animationStep === "result") {
      const timeout = setTimeout(() => {
        setAnimationStep("idle");
        setTimeout(() => setAnimationStep("typing"), 1000);
      }, 6000); // Show result for 6 seconds then reset
      return () => clearTimeout(timeout);
    }
  }, [animationStep]);

  return (
    <div className="min-h-screen bg-[#0D0E12] text-white overflow-hidden selection:bg-[#00e599]/30">
      
      {/* Neon Grid Background */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]"></div>
        <div className="absolute top-0 left-0 right-0 h-[500px] bg-[radial-gradient(circle_800px_at_50%_-100px,#00e59915,transparent)]"></div>
      </div>

      {/* Navbar Placeholder */}
      <nav className="fixed top-0 w-full z-50 border-b border-white/5 bg-[#0D0E12]/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
            <div className="flex items-center gap-2 font-bold text-xl tracking-tighter">
                <div className="w-8 h-8 bg-[#00e599] rounded-lg flex items-center justify-center text-black">
                    <Command size={18} />
                </div>
                DataQuery
            </div>
            <div className="hidden md:flex gap-6 text-sm font-medium text-zinc-400">
                <span className="hover:text-white cursor-pointer transition-colors">Features</span>
                <span className="hover:text-white cursor-pointer transition-colors">Pricing</span>
                <span className="hover:text-white cursor-pointer transition-colors">Docs</span>
            </div>
            <div className="flex gap-4">
                <Link href="/sign-in" className="text-sm font-medium text-zinc-300 hover:text-white pt-2">Login</Link>
                <Link href="/sign-up" className="bg-white text-black px-4 py-2 rounded-full text-sm font-semibold hover:bg-zinc-200 transition-colors">Get Started</Link>
            </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative pt-32 pb-20 md:pt-48 md:pb-32 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto z-10">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          
          {/* Left Column: Copy */}
          <div className="text-left space-y-8">
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#00e599]/10 border border-[#00e599]/20 text-[#00e599] text-xs font-mono font-medium"
            >
              <Zap size={12} />
              <span>AI-NATIVE ANALYTICS</span>
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="text-5xl md:text-7xl font-bold tracking-tight leading-[1.1]"
            >
              Talk to your <br />
              <span className="text-[#00e599]">database.</span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="text-lg text-zinc-400 max-w-xl leading-relaxed"
            >
              Instant insights without the SQL headaches. Connect your data source and start asking questions in plain English immediately.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="flex flex-col sm:flex-row gap-4"
            >
               <SignedOut>
                <Link href="/sign-up">
                  <Button size="lg" className="bg-[#00e599] text-black hover:bg-[#00e599]/90 h-12 px-8 rounded-full font-semibold">
                    Start Building
                    <ArrowRight className="ml-2 w-4 h-4" />
                  </Button>
                </Link>
              </SignedOut>
            </motion.div>
          </div>

          {/* Right Column: Animated Terminal/Chatbot */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.4, duration: 0.5 }}
            className="relative"
          >
            {/* Glow Effect */}
            <div className="absolute -inset-1 bg-gradient-to-r from-[#00e599] to-cyan-500 rounded-2xl blur opacity-20" />
            
            {/* The Window */}
            <div className="relative bg-[#1A1C23] border border-white/10 rounded-xl overflow-hidden shadow-2xl min-h-[400px] flex flex-col">
              
              {/* Window Header */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 bg-[#0D0E12]">
                <div className="flex gap-2">
                  <div className="w-3 h-3 rounded-full bg-red-500/20 border border-red-500/50" />
                  <div className="w-3 h-3 rounded-full bg-yellow-500/20 border border-yellow-500/50" />
                  <div className="w-3 h-3 rounded-full bg-green-500/20 border border-green-500/50" />
                </div>
                <div className="text-xs font-mono text-zinc-500">agent_v2.tsx</div>
                <div className="w-4" />
              </div>

              {/* Window Content */}
              <div className="p-6 font-mono text-sm space-y-6 flex-1 flex flex-col">
                
                {/* Step 1: User Query */}
                {(animationStep !== "idle") && (
                  <div className="flex gap-4">
                    <div className="w-8 h-8 rounded bg-zinc-800 flex items-center justify-center shrink-0">
                      <span className="text-zinc-400">U</span>
                    </div>
                    <div className="space-y-2">
                      <div className="text-[#00e599] text-xs mb-1">USER</div>
                      <div className="text-zinc-100">
                        <TypewriterText 
                          text="Show me the revenue growth for Q3 compared to last year." 
                          onComplete={() => setAnimationStep("thinking")}
                        />
                      </div>
                    </div>
                  </div>
                )}

                {/* Step 2: AI Thinking */}
                {["thinking", "result"].includes(animationStep) && (
                   <div className="flex gap-4">
                    <div className="w-8 h-8 rounded bg-[#00e599]/20 flex items-center justify-center shrink-0">
                      <Sparkles size={14} className="text-[#00e599]" />
                    </div>
                    <div className="w-full space-y-2">
                      <div className="text-[#00e599] text-xs mb-1">AI AGENT</div>
                      
                      {animationStep === "thinking" ? (
                        <div className="flex items-center gap-2 text-zinc-500">
                          <motion.span 
                            animate={{ opacity: [0, 1, 0] }} 
                            transition={{ repeat: Infinity, duration: 1.5 }}
                          >
                            Processing data...
                          </motion.span>
                        </div>
                      ) : (
                        <motion.div 
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          onAnimationComplete={() => {}} // Could trigger next step
                          className="bg-zinc-900/50 border border-white/5 rounded-lg p-4 w-full"
                        >
                          <div className="flex justify-between items-baseline mb-4">
                             <div>
                                <h4 className="text-zinc-400 text-xs uppercase tracking-wider">Total Revenue</h4>
                                <p className="text-2xl font-bold text-white">$1,240,500 <span className="text-[#00e599] text-sm font-normal ml-2">▲ 24%</span></p>
                             </div>
                             <select className="bg-transparent text-xs text-zinc-500 border border-white/10 rounded px-2 py-1">
                                <option>Q3 2024</option>
                             </select>
                          </div>
                          <BarGraph />
                        </motion.div>
                      )}
                    </div>
                  </div>
                )}
              </div>
              
              {/* Input Area (Visual only) */}
              <div className="p-4 border-t border-white/5 bg-[#0D0E12]">
                <div className="flex items-center gap-2 text-zinc-600 bg-zinc-900/50 rounded-lg px-3 py-2 border border-white/5">
                  <Terminal size={14} />
                  <span className="text-xs">Ask a question about your data...</span>
                </div>
              </div>

            </div>
          </motion.div>
        </div>
      </section>

      {/* Bento Grid Features - Dark Mode */}
      <section className="py-24 px-4 bg-[#0D0E12] relative">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">Why developers love us</h2>
            <p className="text-zinc-400">Built for speed, reliability, and security.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 grid-rows-2 gap-4 h-[600px]">
            
            {/* Large Feature */}
            <div className="col-span-1 md:col-span-2 row-span-2 rounded-2xl bg-zinc-900/50 border border-white/10 p-8 flex flex-col justify-between hover:border-[#00e599]/50 transition-colors group relative overflow-hidden">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,#00e59910,transparent_40%)]" />
              <div>
                <div className="w-12 h-12 rounded-full bg-[#00e599]/10 flex items-center justify-center mb-6">
                  <Cpu className="text-[#00e599]" />
                </div>
                <h3 className="text-2xl font-bold mb-2">Serverless Architecture</h3>
                <p className="text-zinc-400">Our engine scales to zero when you aren't using it. Pay only for the queries you run, not for idle time.</p>
              </div>
              <div className="mt-8 flex gap-2">
                 <div className="h-2 w-full bg-zinc-800 rounded-full overflow-hidden">
                    <div className="h-full bg-[#00e599] w-[75%]" />
                 </div>
              </div>
            </div>

            {/* Feature 2 */}
            <div className="col-span-1 md:col-span-2 rounded-2xl bg-zinc-900/50 border border-white/10 p-8 flex items-center justify-between hover:border-[#00e599]/50 transition-colors group">
              <div>
                 <h3 className="text-xl font-bold mb-2">Real-time Sync</h3>
                 <p className="text-zinc-400 text-sm">Postgres, MySQL, and Snowflake supported.</p>
              </div>
              <div className="w-16 h-16 rounded-full border-2 border-dashed border-zinc-700 animate-spin-slow flex items-center justify-center">
                <div className="w-2 h-2 bg-[#00e599] rounded-full" />
              </div>
            </div>

            {/* Feature 3 */}
            <div className="rounded-2xl bg-zinc-900/50 border border-white/10 p-6 hover:border-[#00e599]/50 transition-colors">
              <ShieldCheck className="text-zinc-400 mb-4" />
              <h3 className="text-lg font-bold mb-1">SOC2 Certified</h3>
              <p className="text-zinc-500 text-xs">Enterprise grade security by default.</p>
            </div>

            {/* Feature 4 */}
            <div className="rounded-2xl bg-zinc-900/50 border border-white/10 p-6 hover:border-[#00e599]/50 transition-colors">
              <Terminal className="text-zinc-400 mb-4" />
              <h3 className="text-lg font-bold mb-1">API First</h3>
              <p className="text-zinc-500 text-xs">Integrate into your app with 3 lines of code.</p>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 border-t border-white/10 bg-[#0D0E12]">
        <div className="max-w-7xl mx-auto px-6 flex justify-between items-center text-sm text-zinc-500">
            <p>DataQuery Inc. © 2024</p>
            <div className="flex gap-6">
                <a href="#" className="hover:text-white transition-colors">Twitter</a>
                <a href="#" className="hover:text-white transition-colors">GitHub</a>
                <a href="#" className="hover:text-white transition-colors">Discord</a>
            </div>
        </div>
      </footer>
    </div>
  );
}