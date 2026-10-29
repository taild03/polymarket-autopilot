import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Polymarket AI Autopilot — Next.js Quantitative Command Center",
  description:
    "24/7 AI-Driven Polymarket Quantitative Scanner, Strategy Engine, Risk Manager & Dual Google Argon Failover Router.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className="dark">
      <body className="min-h-screen bg-slate-950 text-slate-100 antialiased">
        {children}
      </body>
    </html>
  );
}
