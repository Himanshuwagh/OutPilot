"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

const QA = [
  { q: "Is it really free?", a: "Yes — Groq free tier, Gmail SMTP, Playwright, and Notion. Zero paid APIs." },
  { q: "Does my Mac need to stay on?", a: "Runs via launchd when awake. Missed runs execute on next wake." },
  { q: "How does email discovery work?", a: "Scrapes company websites, guesses patterns via SMTP, and checks GitHub commits." },
  { q: "Will I get banned from LinkedIn or X?", a: "Random delays, quotas, and persistent sessions minimize risk. Fully configurable." },
  { q: "Can I customize which jobs to target?", a: "Filter by seniority, experience, location, and AI/ML keywords in settings.yaml." },
];

export default function FAQ() {
  const [openIdx, setOpenIdx] = useState<number | null>(null);

  return (
    <section id="faq" className="py-24 md:py-32">
      <div className="mx-auto max-w-[620px] px-6">
        <div className="text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.15em] text-accent">FAQ</p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight md:text-[2.25rem]">
            Common questions
          </h2>
        </div>

        <div className="mt-14 overflow-hidden rounded-2xl border border-border bg-white">
          {QA.map((item, i) => {
            const isOpen = openIdx === i;
            return (
              <motion.div
                key={i}
                initial={false}
                className={i > 0 ? "border-t border-border" : ""}
              >
                <button
                  onClick={() => setOpenIdx(isOpen ? null : i)}
                  className="flex w-full items-center justify-between px-6 py-[18px] text-left transition-colors hover:bg-surface/50"
                >
                  <span className="text-[14px] font-semibold text-foreground">{item.q}</span>
                  <motion.div
                    animate={{ rotate: isOpen ? 45 : 0 }}
                    transition={{ duration: 0.2 }}
                    className={`ml-4 flex h-6 w-6 shrink-0 items-center justify-center rounded-full transition-colors ${isOpen ? "bg-accent text-white" : "bg-surface text-subtle"}`}
                  >
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                      <line x1="6" y1="1" x2="6" y2="11" />
                      <line x1="1" y1="6" x2="11" y2="6" />
                    </svg>
                  </motion.div>
                </button>
                <AnimatePresence initial={false}>
                  {isOpen && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] as const }}
                      className="overflow-hidden"
                    >
                      <p className="px-6 pb-5 text-[13px] leading-relaxed text-muted">
                        {item.a}
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
