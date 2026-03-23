// Stats card with monospace numbers, count-up animation, and skeleton variant.

import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import type { LucideIcon } from "lucide-react";
import Skeleton from "./Skeleton";
import { slideUp } from "../lib/animations";

interface StatsCardProps {
  icon: LucideIcon;
  label: string;
  value: string | number;
  /** Accent color class for the icon, e.g. "text-accent-blue". */
  iconColor?: string;
}

/** Animated number that counts from 0 to target on first render. */
function AnimatedNumber({ value }: { value: number }) {
  const prefersReduced = useReducedMotion();
  const [display, setDisplay] = useState(prefersReduced ? value : 0);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (prefersReduced || value === 0) {
      setDisplay(value);
      return;
    }

    const duration = 600;
    const start = performance.now();
    const from = 0;

    const tick = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic for natural deceleration
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(from + (value - from) * eased));
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(tick);
      }
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [value, prefersReduced]);

  return <>{display.toLocaleString()}</>;
}

/** Single stat card with icon, label, and animated value. */
export default function StatsCard({
  icon: Icon,
  label,
  value,
  iconColor = "text-accent-blue",
}: StatsCardProps) {
  const isNumeric = typeof value === "number";

  return (
    <motion.div
      variants={slideUp}
      className="bg-bg-surface rounded-lg p-4 hover:bg-bg-elevated/50 transition-colors"
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon size={16} className={iconColor} />
        <span className="text-xs text-text-secondary">{label}</span>
      </div>
      <div className="text-3xl font-semibold font-mono tracking-tight">
        {isNumeric ? <AnimatedNumber value={value} /> : value}
      </div>
    </motion.div>
  );
}

/** Skeleton placeholder matching StatsCard dimensions. */
export function StatsCardSkeleton() {
  return (
    <div className="bg-bg-surface rounded-lg p-4">
      <div className="flex items-center gap-2 mb-2">
        <Skeleton width="w-4" height="h-4" className="rounded" />
        <Skeleton width="w-16" height="h-3" />
      </div>
      <Skeleton width="w-20" height="h-8" />
    </div>
  );
}
