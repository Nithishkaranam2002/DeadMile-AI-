"use client";

import { SessionProvider, useSession } from "next-auth/react";
import { useEffect } from "react";
import { registerDriver, setCarrierIdForApi } from "@/lib/config";

function CarrierSync({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession();

  useEffect(() => {
    if (status === "authenticated" && session?.user?.id) {
      setCarrierIdForApi(session.user.id);
      if (session.user.email) {
        registerDriver({
          user_id: session.user.id,
          email: session.user.email,
          name: session.user.name ?? undefined,
        }).catch(() => {});
      }
    } else if (status === "unauthenticated") {
      setCarrierIdForApi("");
    }
  }, [session, status]);

  return <>{children}</>;
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <CarrierSync>{children}</CarrierSync>
    </SessionProvider>
  );
}
