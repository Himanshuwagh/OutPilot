export default function GetStarted() {
  return (
    <section id="get-started" className="bg-surface py-24 md:py-32">
      <div className="mx-auto max-w-[700px] px-6">
        <div className="text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.15em] text-accent">
            Get Started
          </p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight md:text-[2.25rem]">
            Up and running in minutes
          </h2>
        </div>

        {/* Terminal */}
        <div className="mt-14 overflow-hidden rounded-2xl bg-[#0c1222] shadow-2xl shadow-foreground/10 ring-1 ring-white/[0.05]">
          <div className="flex items-center gap-2 border-b border-white/[0.06] px-5 py-3.5">
            <span className="h-3 w-3 rounded-full bg-white/10" />
            <span className="h-3 w-3 rounded-full bg-white/10" />
            <span className="h-3 w-3 rounded-full bg-white/10" />
            <span className="ml-3 text-[11px] font-medium text-white/20">terminal</span>
          </div>
          <div className="space-y-0.5 px-5 py-5 font-mono text-[13px] leading-7">
            <p className="text-white/60"><span className="text-accent">~</span> git clone &lt;repo&gt; &amp;&amp; cd outpilot</p>
            <p className="text-white/60"><span className="text-accent">~</span> pip install -r requirements.txt</p>
            <p className="text-white/60"><span className="text-accent">~</span> cp .env.example .env</p>
            <p className="text-white/60"><span className="text-accent">~</span> python setup_sessions.py <span className="text-white/20"># one-time login</span></p>
            <p className="text-white/60"><span className="text-accent">~</span> python demo.py <span className="text-white/20"># test run</span></p>
          </div>
        </div>

        {/* Config */}
        <div className="mt-8 grid gap-4 sm:grid-cols-3">
          {[
            { title: ".env", items: ["Notion API key", "Groq key (free)", "Gmail app password"] },
            { title: "settings.yaml", items: ["Role preferences", "Location filters", "Daily limits"] },
            { title: "Service", items: ["Run install script", "Daily via launchd", "Zero maintenance"] },
          ].map((c) => (
            <div key={c.title} className="rounded-xl border border-border bg-white p-5">
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
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
