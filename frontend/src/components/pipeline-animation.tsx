"use client";

import { motion, useInView } from "framer-motion";
import { useRef, useState, useEffect } from "react";

const NODES = [
  {
    label: "Scrape",
    sub: "LinkedIn · X · News",
    gradient: "from-teal-400 to-emerald-500",
    iconBg: "bg-gradient-to-br from-teal-400/20 to-emerald-500/20",
    ringColor: "ring-teal-400/30",
    icon: (
      <svg width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="10" />
        <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10" />
      </svg>
    ),
  },
  {
    label: "Filter",
    sub: "AI scores & classifies",
    gradient: "from-cyan-400 to-blue-500",
    iconBg: "bg-gradient-to-br from-cyan-400/20 to-blue-500/20",
    ringColor: "ring-cyan-400/30",
    icon: (
      <svg width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
        <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
      </svg>
    ),
  },
  {
    label: "Discover",
    sub: "Finds contacts & emails",
    gradient: "from-violet-400 to-purple-500",
    iconBg: "bg-gradient-to-br from-violet-400/20 to-purple-500/20",
    ringColor: "ring-violet-400/30",
    icon: (
      <svg width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
        <circle cx="11" cy="11" r="8" />
        <path d="m21 21-4.35-4.35" />
      </svg>
    ),
  },
  {
    label: "Outreach",
    sub: "Personalized cold emails",
    gradient: "from-amber-400 to-orange-500",
    iconBg: "bg-gradient-to-br from-amber-400/20 to-orange-500/20",
    ringColor: "ring-amber-400/30",
    icon: (
      <svg width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
        <line x1="22" y1="2" x2="11" y2="13" />
        <polygon points="22 2 15 22 11 13 2 9 22 2" />
      </svg>
    ),
  },
];

const GRADIENT_COLORS = [
  ["#2dd4bf", "#10b981"],
  ["#22d3ee", "#3b82f6"],
  ["#a78bfa", "#8b5cf6"],
  ["#fbbf24", "#f97316"],
];

export default function PipelineAnimation() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const [activeStep, setActiveStep] = useState(-1);

  useEffect(() => {
    if (!inView) return;
    let step = 0;
    const timer = setInterval(() => {
      setActiveStep(step);
      step++;
      if (step >= NODES.length) {
        clearInterval(timer);
        setTimeout(() => setActiveStep(NODES.length), 600);
      }
    }, 700);
    return () => clearInterval(timer);
  }, [inView]);

  return (
    <div ref={ref} className="mx-auto mt-16 w-full max-w-[720px] px-4">
      {/* Main pipeline container */}
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={inView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] as const }}
        className="relative rounded-2xl border border-border/60 bg-white/70 p-6 shadow-xl shadow-foreground/[0.03] ring-1 ring-white/80 backdrop-blur-sm sm:p-8"
      >
        {/* Ambient glow behind active node */}
        {activeStep >= 0 && activeStep < NODES.length && (
          <motion.div
            key={activeStep}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 0.4, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5 }}
            className="pointer-events-none absolute -z-10 h-28 w-28 rounded-full blur-2xl"
            style={{
              background: `radial-gradient(circle, ${GRADIENT_COLORS[activeStep][0]}40, transparent)`,
              left: `${12.5 + activeStep * 25}%`,
              top: "30%",
              transform: "translateX(-50%)",
            }}
          />
        )}

        {/* Nodes row */}
        <div className="relative flex items-start justify-between">
          {/* Connection line (background track) */}
          <div className="absolute top-8 right-[12.5%] left-[12.5%] z-0 hidden h-[2px] rounded-full bg-border/50 sm:block" />

          {/* Animated progress line */}
          <motion.div
            className="absolute top-8 left-[12.5%] z-[1] hidden h-[2px] origin-left rounded-full sm:block"
            style={{
              background: "linear-gradient(90deg, #2dd4bf, #22d3ee, #a78bfa, #fbbf24)",
              width: "75%",
            }}
            initial={{ scaleX: 0 }}
            animate={activeStep >= 0 ? { scaleX: Math.min((activeStep + 1) / NODES.length, 1) } : { scaleX: 0 }}
            transition={{ duration: 0.6, ease: "easeOut" as const }}
          />

          {/* Travelling particle on the line */}
          {activeStep >= 0 && activeStep < NODES.length && (
            <motion.div
              key={`particle-${activeStep}`}
              className="absolute top-[29px] z-[2] hidden h-2 w-2 rounded-full sm:block"
              style={{
                background: GRADIENT_COLORS[Math.min(activeStep, 3)][0],
                boxShadow: `0 0 10px ${GRADIENT_COLORS[Math.min(activeStep, 3)][0]}`,
              }}
              initial={{ left: `${12.5 + Math.max(activeStep - 1, 0) * 25}%`, opacity: 0 }}
              animate={{ left: `${12.5 + activeStep * 25}%`, opacity: [0, 1, 1, 0.6] }}
              transition={{ duration: 0.6, ease: "easeInOut" as const }}
            />
          )}

          {NODES.map((n, i) => {
            const isActive = activeStep >= i;
            const isCurrent = activeStep === i;

            return (
              <motion.div
                key={n.label}
                initial={{ opacity: 0, y: 16 }}
                animate={inView ? { opacity: 1, y: 0 } : {}}
                transition={{ delay: 0.2 + i * 0.1, duration: 0.5, ease: [0.22, 1, 0.36, 1] as const }}
                className="relative z-10 flex w-1/4 flex-col items-center text-center"
              >
                {/* Icon container */}
                <motion.div
                  animate={
                    isCurrent
                      ? { scale: [1, 1.08, 1], transition: { duration: 0.8, repeat: Infinity, repeatType: "reverse" as const } }
                      : { scale: 1 }
                  }
                  className="relative"
                >
                  {/* Outer ring pulse for active */}
                  {isActive && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.6 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ duration: 0.4 }}
                      className={`absolute -inset-1.5 rounded-2xl ${n.iconBg} ring-2 ${n.ringColor}`}
                    />
                  )}

                  <div
                    className={`relative flex h-14 w-14 items-center justify-center rounded-2xl border transition-all duration-500 sm:h-16 sm:w-16 ${
                      isActive
                        ? "border-transparent bg-white text-foreground shadow-lg"
                        : "border-border bg-surface text-subtle"
                    }`}
                  >
                    {/* Gradient icon color when active */}
                    <div className={isActive ? "text-accent" : "text-subtle"}>
                      {n.icon}
                    </div>

                    {/* Completion checkmark */}
                    {isActive && !isCurrent && activeStep >= NODES.length && (
                      <motion.div
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        transition={{ type: "spring" as const, stiffness: 300, damping: 15 }}
                        className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-gradient-to-br from-accent to-emerald-500 text-white shadow-sm"
                      >
                        <svg width="10" height="10" viewBox="0 0 16 16" fill="none">
                          <path d="M13.333 4 6 11.333 2.667 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </motion.div>
                    )}
                  </div>
                </motion.div>

                {/* Label */}
                <motion.p
                  animate={{ color: isActive ? "#0f172a" : "#94a3b8" }}
                  transition={{ duration: 0.3 }}
                  className="mt-3 text-[12px] font-semibold sm:text-[13px]"
                >
                  {n.label}
                </motion.p>
                <p className={`mt-0.5 text-[10px] transition-colors duration-300 sm:text-[11px] ${isActive ? "text-muted" : "text-subtle/50"}`}>
                  {n.sub}
                </p>
              </motion.div>
            );
          })}
        </div>

        {/* Live status bar at bottom */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={activeStep >= 0 ? { opacity: 1 } : { opacity: 0 }}
          transition={{ duration: 0.4, delay: 0.3 }}
          className="mt-7 flex items-center justify-center gap-2 rounded-xl bg-surface/80 px-4 py-2.5 sm:mt-8"
        >
          {activeStep < NODES.length ? (
            <>
              <motion.span
                animate={{ opacity: [0.4, 1, 0.4] }}
                transition={{ duration: 1.2, repeat: Infinity }}
                className="inline-block h-2 w-2 rounded-full bg-accent"
              />
              <span className="text-[11px] font-medium text-muted sm:text-[12px]">
                {activeStep >= 0 && activeStep < NODES.length
                  ? `Processing: ${NODES[activeStep].label}...`
                  : "Initializing..."}
              </span>
            </>
          ) : (
            <>
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring" as const, stiffness: 300, damping: 12 }}
                className="flex h-4 w-4 items-center justify-center rounded-full bg-accent"
              >
                <svg width="9" height="9" viewBox="0 0 16 16" fill="none">
                  <path d="M13.333 4 6 11.333 2.667 8" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </motion.div>
              <span className="text-[11px] font-semibold text-accent sm:text-[12px]">
                Pipeline complete — 3 emails sent
              </span>
            </>
          )}
        </motion.div>
      </motion.div>
    </div>
  );
}
