"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Github, Settings, Truck } from "lucide-react";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/markets", label: "Markets" },
  { href: "/simulator", label: "Simulator" },
];

export function Navbar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="flex h-14 items-center justify-between px-4 lg:px-6">
        <Link href="/" className="flex items-center gap-2">
          <Truck className="h-6 w-6 text-primary" />
          <span className="bg-gradient-brand bg-clip-text text-lg font-bold text-transparent">
            DeadMile AI
          </span>
        </Link>

        <nav className="hidden items-center gap-6 md:flex">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "text-sm font-medium text-text-secondary transition-colors hover:text-text-primary",
                pathname === link.href && "border-b-2 border-primary pb-0.5 text-primary"
              )}
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <a
            href="https://github.com/Nithishkaranam2002/DeadMile-AI-"
            target="_blank"
            rel="noopener noreferrer"
            className="text-text-secondary hover:text-primary"
          >
            <Github className="h-5 w-5" />
          </a>
          <button className="text-text-secondary hover:text-primary" aria-label="Settings">
            <Settings className="h-5 w-5" />
          </button>
        </div>
      </div>
    </header>
  );
}
