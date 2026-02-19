const ITEMS = [
  "LinkedIn", "X.com", "TechCrunch", "Google News", "Notion", "Gmail",
  "Groq LLM", "Playwright", "SMTP Verify", "GitHub Scrape", "launchd",
  "CrewAI", "DNS Probe", "Dedup Engine",
];

export default function Ticker() {
  return (
    <div className="relative overflow-hidden border-y border-border bg-surface/80 backdrop-blur-sm py-3">
      {/* Fade edges */}
      <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-24 bg-gradient-to-r from-surface to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-24 bg-gradient-to-l from-surface to-transparent" />

      <div className="flex animate-[scroll_30s_linear_infinite] gap-8 whitespace-nowrap">
        {[...ITEMS, ...ITEMS].map((item, i) => (
          <span
            key={i}
            className="flex items-center gap-2 text-[13px] font-medium text-subtle"
          >
            <span className="h-1 w-1 rounded-full bg-accent/40" />
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}
