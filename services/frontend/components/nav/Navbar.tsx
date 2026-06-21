"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signIn, signOut, useSession } from "next-auth/react";
import { Github, LogOut, Menu, Settings, Truck, User, X } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/import", label: "Import" },
  { href: "/compare", label: "Compare" },
  { href: "/markets", label: "Markets" },
  { href: "/simulator", label: "Simulator" },
];

export function Navbar() {
  const pathname = usePathname();
  const { data: session } = useSession();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="flex h-14 items-center justify-between px-4 lg:px-6">
        <Link href="/" className="flex items-center gap-2">
          <Truck className="h-6 w-6 text-primary" />
          <span className="bg-gradient-brand bg-clip-text text-lg font-bold text-transparent">
            DeadMile AI
          </span>
        </Link>

        <nav className="hidden items-center gap-5 md:flex">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "text-sm font-medium text-text-secondary transition-colors hover:text-text-primary",
                isActive(link.href) && "border-b-2 border-primary pb-0.5 text-primary"
              )}
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          {session?.user ? (
            <div className="hidden items-center gap-2 sm:flex">
              <div className="flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1">
                <User className="h-4 w-4 text-primary" />
                <span className="max-w-[120px] truncate text-sm">
                  {session.user.name || session.user.email}
                </span>
              </div>
              <Link
                href="/settings"
                className="text-text-secondary hover:text-primary"
                aria-label="Fleet Settings"
              >
                <Settings className="h-5 w-5" />
              </Link>
              <button
                type="button"
                onClick={() => signOut({ callbackUrl: "/" })}
                className="text-text-secondary hover:text-danger"
                aria-label="Sign out"
              >
                <LogOut className="h-5 w-5" />
              </button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="outline"
              className="hidden sm:inline-flex"
              onClick={() => signIn(undefined, { callbackUrl: "/" })}
            >
              Sign In
            </Button>
          )}

          <a
            href="https://github.com/Nithishkaranam2002/DeadMile-AI-"
            target="_blank"
            rel="noopener noreferrer"
            className="hidden text-text-secondary hover:text-primary sm:block"
          >
            <Github className="h-5 w-5" />
          </a>

          <button
            type="button"
            className="md:hidden"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label="Menu"
          >
            {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
          </button>
        </div>
      </div>

      {mobileOpen && (
        <nav className="border-t border-border bg-surface px-4 py-3 md:hidden">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "block py-2 text-sm font-medium",
                isActive(link.href) ? "text-primary" : "text-text-secondary"
              )}
              onClick={() => setMobileOpen(false)}
            >
              {link.label}
            </Link>
          ))}
          {session?.user ? (
            <button
              type="button"
              className="mt-2 flex w-full items-center gap-2 py-2 text-sm text-text-secondary"
              onClick={() => signOut({ callbackUrl: "/" })}
            >
              <LogOut className="h-4 w-4" /> Sign out
            </button>
          ) : (
            <Button
              size="sm"
              className="mt-2 w-full"
              onClick={() => {
                setMobileOpen(false);
                signIn(undefined, { callbackUrl: "/" });
              }}
            >
              Sign In
            </Button>
          )}
        </nav>
      )}
    </header>
  );
}
