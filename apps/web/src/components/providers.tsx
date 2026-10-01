"use client";

import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { useState } from "react";
import { toast } from "sonner";

import { Notifier } from "@/components/notifier";
import { Toaster } from "@/components/ui/sonner";

declare module "@tanstack/react-query" {
  interface Register {
    /** action names what failed in its toast; quiet is for a mutation whose result pane already
     * shows its error in place. */
    mutationMeta: { action?: string; quiet?: boolean };
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
            if (mutation.meta?.quiet) return;
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
        {children}
        <Notifier />
        <Toaster position="bottom-right" closeButton />
      </NuqsAdapter>
    </QueryClientProvider>
  );
}
