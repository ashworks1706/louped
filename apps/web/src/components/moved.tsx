"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";

import { part } from "@/components/parts";
import { MOVED } from "@/lib/nav";

/** Where an old /behavior/ or /efficiency/ address is now, with its query kept. */
export function movedTo(pathname: string, search: string): string {
  const path = pathname.endsWith("/") ? pathname : `${pathname}/`;
  const to = MOVED[path] ?? "/";
  const [base, own] = to.split("?");
  const query = new URLSearchParams(own);
  new URLSearchParams(search).forEach((v, k) => query.set(k, v));
  const q = query.toString();
  return q ? `${base}?${q}` : base;
}

/** An old address: replaces itself with the page's new one, so history keeps no dead entry. */
export function Moved() {
  const router = useRouter();
  const to = movedTo(usePathname(), useSearchParams().toString());
  useEffect(() => router.replace(to), [router, to]);
  return (
    <p className="text-muted-foreground mx-auto max-w-6xl px-6 py-8 text-sm">
      This page moved to{" "}
      <Link href={to} {...part("moved")}>
        {to}
      </Link>
      .
    </p>
  );
}
