import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { FleetCostBanner } from "@/components/FleetCostBanner";
import { Navbar } from "@/components/nav/Navbar";
import { StatusBar } from "@/components/nav/StatusBar";
import { Providers } from "@/components/providers/Providers";
import { ServiceWorkerRegister } from "@/components/providers/ServiceWorkerRegister";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const jetbrains = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains" });

export const metadata = {
  title: "DeadMile AI — Intelligent Load Optimization",
  description: "AI-powered trucking load optimization with true net profitability. 100% free.",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent" as const,
    title: "DeadMile AI",
  },
  themeColor: "#22D3EE",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="apple-touch-icon" href="/icons/icon-192.png" />
      </head>
      <body className={`${inter.variable} ${jetbrains.variable} flex min-h-screen flex-col font-sans`}>
        <Providers>
          <ServiceWorkerRegister />
          <Navbar />
          <FleetCostBanner />
          <main className="flex-1">{children}</main>
          <StatusBar />
        </Providers>
      </body>
    </html>
  );
}
