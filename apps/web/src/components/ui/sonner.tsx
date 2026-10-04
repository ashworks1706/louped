"use client";

import { useTheme } from "next-themes";
import { Toaster as Sonner, type ToasterProps } from "sonner";

/** shadcn's Sonner, on louped's tokens: popover surface, border, Geist, the ring on focus, and the
 * negative token only on an error's icon. */
function Toaster(props: ToasterProps) {
  const { resolvedTheme } = useTheme();
  return (
    <Sonner
      theme={resolvedTheme === "light" ? "light" : "dark"}
      className="toaster !font-sans"
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "group focus-visible:!ring-ring/50 focus-visible:!ring-[3px] !outline-none",
          description: "!text-muted-foreground text-xs",
          icon: "group-data-[type=error]:text-negative",
          actionButton:
            "!bg-primary !text-primary-foreground focus-visible:!ring-ring/50 focus-visible:!ring-[3px] !outline-none",
          closeButton: "focus-visible:!ring-ring/50 focus-visible:!ring-[3px] !outline-none",
        },
      }}
      {...props}
    />
  );
}

export { Toaster };
