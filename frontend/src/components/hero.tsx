"use client";

import { motion } from "framer-motion";
import AnimatedCounter from "./animated-counter";

export default function Hero() {
  return (
    <section className="relative flex min-h-[100dvh] items-center justify-center overflow-hidden">
      {/* Hero: one soft highlight so global sky stays the focus */}
      <div className="pointer-events-none absolute inset-0 -z-10">
        <motion.div
          animate={{
            opacity: [0.4, 0.6, 0.4],
            scale: [1, 1.03, 1],
          }}
          transition={{ duration: 14, repeat: Infinity, ease: "easeInOut" }}
          className="absolute top-0 left-1/2 h-[420px] w-[800px] -translate-x-1/2 -translate-y-1/4 rounded-full bg-gradient-to-b from-white/30 via-teal-50/20 to-transparent blur-3xl"
        />
      </div>

      <div className="mx-auto w-full max-w-[1000px] px-6 pt-14 text-center">
        {/* Badge */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="inline-flex items-center gap-2 rounded-full border border-teal-500/30 bg-teal-950/50 backdrop-blur-md px-3.5 py-1 text-[13px] font-medium text-teal-200"
        >
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-teal-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-teal-400" />
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
          className="mx-auto mt-6 max-w-[460px] text-base leading-relaxed text-slate-200"
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
            className="group inline-flex items-center gap-2 rounded-full bg-white px-6 py-2.5 text-sm font-semibold text-slate-900 transition-all hover:bg-white/90 hover:shadow-lg hover:shadow-white/10"
          >
            Get Started
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:translate-x-0.5">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </a>
          <a
            href="#how-it-works"
            className="rounded-full border border-white/20 bg-white/5 backdrop-blur-sm px-6 py-2.5 text-sm font-semibold text-white transition-all hover:border-white/40 hover:bg-white/10"
          >
            How It Works
          </a>
        </motion.div>

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
