"use client";

import { motion } from "framer-motion";
import PipelineAnimation from "./pipeline-animation";
import AnimatedCounter from "./animated-counter";

export default function Hero() {
  return (
    <section className="relative flex min-h-[100dvh] items-center justify-center overflow-hidden">
      {/* Background */}
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute top-0 left-1/2 h-[600px] w-[900px] -translate-x-1/2 -translate-y-1/4 rounded-full bg-accent/[0.04] blur-3xl" />
        <div className="absolute bottom-0 right-0 h-[300px] w-[400px] translate-x-1/4 rounded-full bg-accent/[0.03] blur-3xl" />
      </div>

      <div className="mx-auto w-full max-w-[1000px] px-6 pt-14 text-center">
        {/* Badge */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="inline-flex items-center gap-2 rounded-full border border-accent/20 bg-accent-light px-3.5 py-1 text-[13px] font-medium text-accent-hover"
        >
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
          </span>
          Free &amp; fully local
        </motion.div>

        {/* Heading */}
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="mt-8 text-[clamp(2.5rem,6vw,4rem)] font-bold leading-[1.08] tracking-[-0.03em] text-foreground"
        >
          Your AI/ML job search,
          <br />
          <span className="text-accent">on autopilot</span>
        </motion.h1>

        {/* Subtitle */}
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="mx-auto mt-6 max-w-[460px] text-base leading-relaxed text-muted"
        >
          Outpilot scrapes jobs from LinkedIn, X &amp; tech news — finds
          contacts, discovers emails, and sends personalized outreach.
        </motion.p>

        {/* CTAs */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3 }}
          className="mt-10 flex items-center justify-center gap-3"
        >
          <a
            href="#get-started"
            className="group inline-flex items-center gap-2 rounded-full bg-foreground px-6 py-2.5 text-sm font-semibold text-white transition-all hover:bg-foreground/90 hover:shadow-lg hover:shadow-foreground/10"
          >
            Get Started
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:translate-x-0.5">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </a>
          <a
            href="#how-it-works"
            className="rounded-full border border-border px-6 py-2.5 text-sm font-semibold text-foreground transition-all hover:border-border/80 hover:bg-surface"
          >
            How It Works
          </a>
        </motion.div>

        {/* Pipeline explainer animation */}
        <PipelineAnimation />

        {/* Animated stats */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 1.8 }}
          className="mx-auto mt-14 grid max-w-sm grid-cols-3 divide-x divide-border"
        >
          {[
            { end: 5, suffix: "+", label: "Sources" },
            { end: 0, prefix: "$", label: "Cost" },
            { end: 24, suffix: "h", label: "Cycle" },
          ].map((s) => (
            <div key={s.label} className="px-4 text-center">
              <AnimatedCounter end={s.end} prefix={s.prefix} suffix={s.suffix} />
              <p className="mt-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-subtle">
                {s.label}
              </p>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
