"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4 px-4 text-center">
      <h2 className="text-xl font-bold text-text-primary">Something went wrong</h2>
      <p className="max-w-md text-sm text-text-secondary">{error.message || "An unexpected error occurred."}</p>
      <Button onClick={() => reset()}>Try again</Button>
    </div>
  );
}
