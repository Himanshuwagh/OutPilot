import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

const sans = Plus_Jakarta_Sans({
  variable: "--font-sans",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Outpilot — AI/ML Job Outreach on Autopilot",
  description:
    "Automated pipeline that finds AI/ML jobs, discovers contacts, and sends personalized cold emails. Free, local, and fully automated on your Mac.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={sans.variable}>
      <body className="antialiased">
        <div className="fixed inset-0 -z-10 h-full w-full bg-slate-950">
          <div
            className="absolute inset-0 bg-cover bg-center bg-no-repeat opacity-60 blur-[2px]"
            style={{ backgroundImage: 'url(/background.jpg)' }}
          />
          {/* Heavy gradient overlay for maximum contrast */}
          <div className="absolute inset-0 bg-gradient-to-b from-black/70 via-black/50 to-slate-950" />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,rgba(0,0,0,0.4)_100%)]" />
        </div>
        {children}
      </body>
    </html>
  );
}
