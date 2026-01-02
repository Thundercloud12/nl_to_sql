"use client";

import dynamic from 'next/dynamic';
import { motion } from 'framer-motion';
import { BarChart3 } from 'lucide-react';

import { useTheme } from "next-themes";

// Dynamically import Plotly to avoid SSR issues
const Plot = dynamic(() => import('react-plotly.js'), { 
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[400px] bg-muted/50 dark:bg-black/40 rounded-lg border border-border dark:border-white/5">
      <div className="text-muted-foreground dark:text-zinc-500 text-sm font-mono">Loading chart...</div>
    </div>
  )
});

interface ChartProps {
  data: any;  // Plotly JSON spec
}

export function Chart({ data }: ChartProps) {
  const { theme } = useTheme();
  
  console.log("[CHART COMPONENT] Chart component mounted with data:", data);
  
  if (!data) {
    console.log("[CHART COMPONENT] ❌ No data provided");
    return null;
  }
  
  if (!data.data) {
    console.log("[CHART COMPONENT] ❌ No data.data field found");
    console.log("[CHART COMPONENT] Available keys:", Object.keys(data));
    return null;
  }

  console.log("[CHART COMPONENT] ✓ Rendering chart");
  console.log("[CHART COMPONENT] data.data length:", data.data?.length);
  console.log("[CHART COMPONENT] data.layout:", data.layout);
  
  const isDark = theme === "dark";

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
      className="mt-4 p-4 bg-white/50 dark:bg-black/40 rounded-lg border border-primary/20 dark:border-[#00e599]/20 overflow-hidden backdrop-blur-sm"
    >
      {/* Chart Header */}
      <div className="flex items-center gap-2 mb-3 pb-3 border-b border-border dark:border-white/5">
        <BarChart3 size={16} className="text-primary dark:text-[#00e599]" />
        <span className="text-xs font-mono text-muted-foreground dark:text-zinc-400 uppercase tracking-wider">
          Visualization
        </span>
      </div>
      
      {/* Plotly Chart */}
      <div className="w-full">
        <Plot
          data={data.data}
          layout={{
            ...data.layout,
            autosize: true,
            margin: { l: 60, r: 40, t: 50, b: 60 },
            // Ensure theme awareness
            plot_bgcolor: 'rgba(0,0,0,0)',
            paper_bgcolor: 'rgba(0,0,0,0)',
            font: { 
              color: isDark ? 'white' : '#1d1d1f',
              family: 'ui-monospace, monospace'
            },
            // Style axes
            xaxis: {
              ...data.layout?.xaxis,
              gridcolor: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)',
              linecolor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
            },
            yaxis: {
              ...data.layout?.yaxis,
              gridcolor: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)',
              linecolor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
            },
          }}
          config={{
            displayModeBar: true,
            displaylogo: false,
            responsive: true,
            modeBarButtonsToRemove: ['pan2d', 'lasso2d', 'select2d'],
            modeBarButtonsToAdd: [],
            toImageButtonOptions: {
              format: 'png',
              filename: 'chart',
              height: 800,
              width: 1200,
              scale: 2
            }
          }}
          style={{ 
            width: '100%', 
            height: '400px'
          }}
          className="plotly-chart"
        />
      </div>
      
      {/* Footer note */}
      <div className="mt-3 pt-3 border-t border-border dark:border-white/5 text-xs text-muted-foreground dark:text-zinc-600 font-mono text-center">
        Interactive • Hover for details • Click and drag to zoom
      </div>
    </motion.div>
  );
}
