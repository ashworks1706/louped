"use client";

import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { useState } from "react";
import { toast } from "sonner";

import { Notifier } from "@/components/notifier";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

declare module "@tanstack/react-query" {
  interface Register {
    /** action names what failed in its toast; quiet is for a mutation that shows its error in
     * place (its result pane, a dialog), always or for the errors it picks. */
    mutationMeta: { action?: string; quiet?: boolean | ((error: Error) => boolean) };
  }
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 10_000, retry: 1, refetchOnWindowFocus: true } },
        // Every failed action says so, with the server's own message.
        mutationCache: new MutationCache({
          onError: (error, _vars, _ctx, mutation) => {
            const quiet = mutation.meta?.quiet;
            if (typeof quiet === "function" ? quiet(error) : quiet) return;
            toast.error(`${mutation.meta?.action ?? "Request"} failed`, {
              description: error.message,
              duration: Infinity,
            });
          },
        }),
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <NuqsAdapter>
        <TooltipProvider>
          {children}
          <Notifier />
          <Toaster position="bottom-right" closeButton />
        </TooltipProvider>
      </NuqsAdapter>
    </QueryClientProvider>
  );
}
