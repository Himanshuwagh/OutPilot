import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
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
    <html lang="en" className={inter.variable}>
      <body className="antialiased">
        <div className="gradient-bg" aria-hidden="true">
          <div className="accent-band" />
          <div className="orb orb-1" />
          <div className="orb orb-2" />
          <div className="orb orb-3" />
          <div className="orb orb-4" />
        </div>
        {children}
      </body>
    </html>
  );
}
