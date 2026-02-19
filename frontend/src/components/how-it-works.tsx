"use client";

import { motion } from "framer-motion";

const STEPS = [
  {
    n: "01",
    title: "Scrape",
    desc: "Pulls fresh AI/ML posts daily from LinkedIn, X & tech news.",
    icon: (
      <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
        <path d="M21 12a9 9 0 0 1-9 9m9-9a9 9 0 0 0-9-9m9 9H3m9 9a9 9 0 0 1-9-9m9 9c1.66 0 3-4.03 3-9s-1.34-9-3-9m0 18c-1.66 0-3-4.03-3-9s1.34-9 3-9m-9 9a9 9 0 0 1 9-9" />
      </svg>
    ),
  },
  {
    n: "02",
    title: "Filter",
    desc: "Scores posts, drops noise, senior roles & US-only positions.",
    icon: (
      <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
        <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
      </svg>
    ),
  },
  {
    n: "03",
    title: "Discover",
    desc: "Finds company domains, contacts, and verifies their emails.",
    icon: (
      <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
        <circle cx="11" cy="11" r="8" />
        <path d="m21 21-4.35-4.35" />
      </svg>
    ),
  },
  {
    n: "04",
    title: "Send",
    desc: "LLM drafts personalized emails. Top-scored go out via Gmail.",
    icon: (
      <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
        <line x1="22" y1="2" x2="11" y2="13" />
        <polygon points="22 2 15 22 11 13 2 9 22 2" />
      </svg>
    ),
  },
];

const cardVariant = {
  hidden: { opacity: 0, y: 28, scale: 0.95 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    scale: 1,
    transition: {
      delay: i * 0.15,
      duration: 0.55,
      ease: [0.22, 1, 0.36, 1] as const,
    },
  }),
};

const lineGrow = {
  hidden: { scaleX: 0 },
  show: (i: number) => ({
    scaleX: 1,
    transition: { delay: i * 0.15 + 0.25, duration: 0.5, ease: "easeOut" as const },
  }),
};

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="section-glow py-24 md:py-32">
      <div className="mx-auto max-w-[1000px] px-6">
        <div className="text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.15em] text-accent">
            How It Works
          </p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight md:text-[2.25rem]">
            Four steps, fully automated
          </h2>
        </div>

        <div className="mt-16 grid gap-5 sm:grid-cols-2 md:grid-cols-4">
          {STEPS.map((s, i) => (
            <div key={s.n} className="relative">
              {/* Animated connector line between cards */}
              {i < STEPS.length - 1 && (
                <motion.div
                  custom={i}
                  variants={lineGrow}
                  initial="hidden"
                  whileInView="show"
                  viewport={{ once: true }}
                  className="absolute right-0 top-8 z-10 hidden h-px w-5 origin-left bg-accent/30 translate-x-full md:block"
                />
              )}

              <motion.div
                custom={i}
                variants={cardVariant}
                initial="hidden"
                whileInView="show"
                viewport={{ once: true, margin: "-40px" }}
                whileHover={{
                  y: -6,
                  boxShadow: "0 12px 32px -8px rgba(20,184,166,0.12)",
                  borderColor: "rgba(20,184,166,0.25)",
                  transition: { duration: 0.25 },
                }}
                className="group relative rounded-2xl border border-white/5 bg-white/5 p-6 backdrop-blur-sm"
              >
                <div className="flex items-center justify-between">
                  <motion.div
                    className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-light text-accent"
                    whileHover={{ scale: 1.1, rotate: 6 }}
                    transition={{ type: "spring", stiffness: 300 }}
                  >
                    {s.icon}
                  </motion.div>
                  <span className="text-[11px] font-bold tracking-widest text-subtle">{s.n}</span>
                </div>
                <h3 className="mt-5 text-base font-semibold text-foreground">{s.title}</h3>
                <p className="mt-2 text-[13px] leading-relaxed text-muted">{s.desc}</p>
              </motion.div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
