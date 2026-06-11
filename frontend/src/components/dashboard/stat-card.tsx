"use client";

import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  hint?: string;
  tone?: "primary" | "accent" | "secondary" | "warning";
  delay?: number;
}

const TONES = {
  primary: "bg-primary/10 text-primary",
  accent: "bg-accent/10 text-accent",
  secondary: "bg-secondary/10 text-secondary dark:bg-secondary/40 dark:text-secondary-foreground",
  warning: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
};

export function StatCard({ label, value, icon: Icon, hint, tone = "primary", delay = 0 }: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: "easeOut" }}
    >
      <Card>
        <CardContent className="flex items-center gap-4 p-5">
          <div className={cn("flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl", TONES[tone])}>
            <Icon className="h-6 w-6" />
          </div>
          <div className="min-w-0">
            <p className="text-sm text-muted-foreground">{label}</p>
            <p className="text-2xl font-bold tracking-tight">{value}</p>
            {hint && <p className="truncate text-xs text-muted-foreground">{hint}</p>}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
