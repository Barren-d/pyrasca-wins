"use client";

import { useSyncExternalStore } from "react";
import { THEME_KEY } from "@/lib/theme";

const media = () => window.matchMedia("(prefers-color-scheme: dark)");

/** The theme actually shown: the saved choice, else the device setting. */
function currentTheme(): "dark" | "light" {
  const picked = document.documentElement.dataset.theme;
  if (picked === "dark" || picked === "light") return picked;
  return media().matches ? "dark" : "light";
}

function subscribe(onChange: () => void) {
  const mq = media();
  mq.addEventListener("change", onChange);
  window.addEventListener("pyrasca-theme", onChange);
  return () => {
    mq.removeEventListener("change", onChange);
    window.removeEventListener("pyrasca-theme", onChange);
  };
}

/** Sun/moon button: switches to the other theme and remembers the choice on this device. */
export function ThemeToggle({ toDark, toLight }: { toDark: string; toLight: string }) {
  // null while prerendering: the server can't know the visitor's theme
  const theme = useSyncExternalStore(subscribe, currentTheme, () => null);

  const toggle = () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // storage blocked: the switch still applies to this page view
    }
    window.dispatchEvent(new Event("pyrasca-theme"));
  };

  const label = theme === "dark" ? toLight : toDark;
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={label}
      className="flex h-11 w-11 cursor-pointer items-center justify-center rounded-full border border-line bg-card text-ink hover:border-control"
    >
      {theme === "dark" ? (
        // sun: shown in dark mode, switches to light
        <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
        </svg>
      ) : (
        // moon: shown in light mode (and while the theme is still unknown)
        <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      )}
    </button>
  );
}
