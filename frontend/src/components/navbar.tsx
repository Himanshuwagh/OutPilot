"use client";

import { useEffect, useState } from "react";

const LINKS = [
  { label: "Features", href: "#features" },
  { label: "How It Works", href: "#how-it-works" },
  { label: "FAQ", href: "#faq" },
];

export default function Navbar() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 transition-all duration-300 ${
        scrolled
          ? "bg-white/90 shadow-sm shadow-foreground/[0.03] backdrop-blur-xl"
          : "bg-transparent"
      }`}
    >
      <div className="mx-auto flex h-[56px] max-w-[1000px] items-center justify-between px-6">
        <a href="#" className="flex items-center gap-2.5">
          <div className="relative flex h-7 w-7 items-center justify-center overflow-hidden rounded-lg bg-accent">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </div>
          <span className="text-[15px] font-semibold tracking-[-0.01em] text-foreground">Outpilot</span>
        </a>

        <div className="hidden items-center gap-8 md:flex">
          {LINKS.map((l) => (
            <a key={l.href} href={l.href} className="text-[13px] font-medium text-muted transition-colors hover:text-foreground">
              {l.label}
            </a>
          ))}
          <a
            href="#get-started"
            className="rounded-full bg-foreground px-4 py-[7px] text-[13px] font-medium text-white transition-all hover:bg-foreground/90 hover:shadow-sm"
          >
            Get Started
          </a>
        </div>

        <button
          onClick={() => setOpen(!open)}
          className="grid h-8 w-8 place-items-center rounded-lg text-muted md:hidden"
          aria-label="Menu"
        >
          <svg width="18" height="12" viewBox="0 0 18 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            {open ? (
              <>
                <line x1="2" y1="1" x2="16" y2="11" />
                <line x1="2" y1="11" x2="16" y2="1" />
              </>
            ) : (
              <>
                <line x1="0" y1="1" x2="18" y2="1" />
                <line x1="0" y1="6" x2="18" y2="6" />
                <line x1="0" y1="11" x2="18" y2="11" />
              </>
            )}
          </svg>
        </button>
      </div>

      {open && (
        <div className="bg-white px-6 pb-5 pt-1 shadow-lg md:hidden">
          {LINKS.map((l) => (
            <a key={l.href} href={l.href} onClick={() => setOpen(false)} className="block py-3 text-sm text-muted">
              {l.label}
            </a>
          ))}
          <a href="#get-started" onClick={() => setOpen(false)} className="mt-2 block rounded-full bg-foreground py-2.5 text-center text-sm font-medium text-white">
            Get Started
          </a>
        </div>
      )}
    </header>
  );
}
