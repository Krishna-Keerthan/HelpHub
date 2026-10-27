import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { resetSessionCache } from "@/lib/query/client";

afterEach(() => {
  cleanup();
  resetSessionCache();
  if (typeof sessionStorage !== "undefined") sessionStorage.clear();
  vi.unstubAllGlobals();
});
