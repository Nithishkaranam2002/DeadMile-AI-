import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorBoundary } from "@/components/ErrorBoundary";

const LoadMapInner = dynamic(() => import("./LoadMap").then((m) => m.LoadMap), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full min-h-[400px]" />,
});

export function LoadMapDynamic() {
  return (
    <ErrorBoundary fallbackTitle="Map failed to load">
      <LoadMapInner />
    </ErrorBoundary>
  );
}
