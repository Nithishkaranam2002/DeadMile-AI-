import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DeadMile AI — Intelligent Load Optimization",
  description:
    "AI-powered platform that helps small trucking carriers maximize profitability by eliminating dead miles.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
