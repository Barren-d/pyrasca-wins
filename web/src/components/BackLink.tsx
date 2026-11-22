"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

const KEY = "pyrasca-inapp-nav";

/**
 * Notes (per browser tab) that the visitor has moved between pages of this site, so
 * BackLink knows the previous history entry is one of ours. Rendered once in the layout.
 */
export function NavTracker() {
  const pathname = usePathname();
  useEffect(() => {
    try {
      const seen = sessionStorage.getItem(`${KEY}-first`);
      if (seen === null) sessionStorage.setItem(`${KEY}-first`, pathname);
      else if (seen !== pathname) sessionStorage.setItem(KEY, "1");
    } catch {
      // storage unavailable (private mode): BackLink falls back to a plain link
    }
  }, [pathname]);
  return null;
}

/**
 * "Back" that returns to the previous page as it was (scroll position, filters,
 * sort), via browser history, when the visitor came from within the site.
 * Otherwise (a shared link, a new tab) it opens `fallback`.
 */
export function BackLink({ fallback, children, className }: { fallback: string; children: React.ReactNode; className?: string }) {
  const router = useRouter();
  const onClick = (e: React.MouseEvent) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return; // new tab/window: plain link
    let inApp = false;
    try {
      inApp = sessionStorage.getItem(KEY) === "1" && window.history.length > 1;
    } catch {}
    if (inApp) {
      e.preventDefault();
      router.back();
    }
  };
  return (
    <Link href={fallback} onClick={onClick} className={className}>
      {children}
    </Link>
  );
}
