"use client";

import { useEffect, useState } from "react";

type Theme = "system" | "light" | "dark";
const STORAGE_KEY = "agency-os-theme";
const options: { value: Theme; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

export default function ThemeControl() {
  const [theme, setTheme] = useState<Theme>("system");

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      const initial: Theme = stored === "light" || stored === "dark" ? stored : "system";
      setTheme(initial);
      applyTheme(initial);
    } catch {
      applyTheme("system");
    }
  }, []);

  function selectTheme(nextTheme: Theme) {
    setTheme(nextTheme);
    applyTheme(nextTheme);
    try {
      if (nextTheme === "system") window.localStorage.removeItem(STORAGE_KEY);
      else window.localStorage.setItem(STORAGE_KEY, nextTheme);
    } catch {
      // The selected theme still applies for this session when storage is unavailable.
    }
  }

  return (
    <div className="theme-control" role="group" aria-label="Color theme">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className="theme-option"
          aria-pressed={theme === option.value}
          onClick={() => selectTheme(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
