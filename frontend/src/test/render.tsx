import { QueryClientProvider } from "@tanstack/react-query";
import { render as rtlRender, type RenderOptions } from "@testing-library/react";
import type { ReactElement } from "react";
import { getQueryClient } from "@/lib/query/client";

/** `render` with the same in-memory query client the app uses (cleared after every test in setup.ts). */
export function render(ui: ReactElement, options?: Omit<RenderOptions, "wrapper">) {
  return rtlRender(ui, {
    wrapper: ({ children }) => <QueryClientProvider client={getQueryClient()}>{children}</QueryClientProvider>,
    ...options,
  });
}
