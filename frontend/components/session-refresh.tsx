"use client";

import { useEffect } from "react";
import { refreshBrowserSession } from "@/lib/api";

const REFRESH_INTERVAL_MS = 15 * 60 * 1000;

export default function SessionRefresh() {
  useEffect(() => {
    void refreshBrowserSession(true);
    const interval = window.setInterval(() => {
      void refreshBrowserSession(true);
    }, REFRESH_INTERVAL_MS);
    const handleVisibility = () => {
      if (document.visibilityState === "visible") void refreshBrowserSession();
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, []);

  return null;
}
