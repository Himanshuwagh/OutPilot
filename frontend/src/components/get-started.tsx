"use client";

import { motion, useInView } from "framer-motion";
import { useRef, useState, useEffect } from "react";

const LINES = [
  { prompt: true, text: "git clone https://github.com/Himanshuwagh/OutPilot && cd OutPilot" },
  { prompt: true, text: "pip install -r requirements.txt" },
  { prompt: true, text: "cp .env.example .env" },
  { prompt: true, text: "python setup_sessions.py", comment: "# one-time login" },
  { prompt: true, text: "python demo.py", comment: "# test run" },
];

const CONFIG = [
  { title: ".env", items: ["Notion API key", "Groq key (free)", "Gmail app password"] },
  { title: "settings.yaml", items: ["Role preferences", "Location filters", "Daily limits"] },
  { title: "Service", items: ["Run install script", "Daily via launchd", "Zero maintenance"] },
];

function TypingTerminal() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });
  const [visibleLines, setVisibleLines] = useState(0);

  useEffect(() => {
    if (!inView) return;
    let line = 0;
    const interval = setInterval(() => {
      line++;
      setVisibleLines(line);
      if (line >= LINES.length) clearInterval(interval);
    }, 450);
    return () => clearInterval(interval);
  }, [inView]);

  return (
    <div ref={ref} className="mt-14 overflow-hidden rounded-2xl bg-[#0c1222] shadow-2xl shadow-foreground/10 ring-1 ring-white/[0.05]">
      <div className="flex items-center gap-2 border-b border-white/[0.06] px-5 py-3.5">
        <span className="h-3 w-3 rounded-full bg-white/10" />
        <span className="h-3 w-3 rounded-full bg-white/10" />
        <span className="h-3 w-3 rounded-full bg-white/10" />
        <span className="ml-3 text-[11px] font-medium text-white/20">terminal</span>
      </div>
      <div className="space-y-0.5 px-5 py-5 font-mono text-[13px] leading-7">
        {LINES.map((l, i) => (
          <motion.p
            key={i}
            initial={{ opacity: 0, x: -8 }}
            animate={i < visibleLines ? { opacity: 1, x: 0 } : {}}
            transition={{ duration: 0.3 }}
            className="text-white/60"
          >
            {l.prompt && <span className="text-accent">~</span>}{" "}
            {l.text}
            {l.comment && <span className="text-white/20"> {l.comment}</span>}
          </motion.p>
        ))}
        {visibleLines >= LINES.length && (
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 1, 0] }}
            transition={{ duration: 1, repeat: Infinity }}
            className="inline-block h-4 w-2 translate-y-0.5 bg-accent"
          />
        )}
      </div>
    </div>
  );
}

const configCard = {
  hidden: { opacity: 0, y: 16 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.12, duration: 0.45, ease: [0.22, 1, 0.36, 1] as const },
  }),
};

export default function GetStarted() {
  return (
    <section id="get-started" className="section-glow py-24 md:py-32">
      <div className="mx-auto max-w-[700px] px-6">
        <div className="text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.15em] text-accent">
            Get Started
          </p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight md:text-[2.25rem]">
            Up and running in minutes
          </h2>
        </div>

        <TypingTerminal />

        <div className="mt-8 grid gap-4 sm:grid-cols-3">
          {CONFIG.map((c, i) => (
            <motion.div
              key={c.title}
              custom={i}
              variants={configCard}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true }}
              whileHover={{ y: -4, transition: { duration: 0.2 } }}
              className="rounded-xl border border-white/5 bg-white/5 p-5 backdrop-blur-sm"
            >
              <h3 className="text-sm font-semibold text-foreground">{c.title}</h3>
              <ul className="mt-3 space-y-2.5">
                {c.items.map((item) => (
                  <li key={item} className="flex items-center gap-2.5 text-[13px] text-muted">
                    <div className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-accent/10">
                      <svg width="10" height="10" viewBox="0 0 16 16" fill="none" className="text-accent">
                        <path d="M13.333 4 6 11.333 2.667 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </div>
                    {item}
                  </li>
                ))}
              </ul>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
