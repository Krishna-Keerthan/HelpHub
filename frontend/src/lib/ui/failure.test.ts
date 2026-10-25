import { expect, test } from "vitest";
import { MAX_UPLOAD_BYTES, safeNext, uploadTooLargeMessage } from "./failure";

test("safeNext accepts only same-site paths", () => {
  expect(safeNext("/chat?x=1")).toBe("/chat?x=1");
  for (const bad of ["//evil.test", "https://evil.test", "/\\evil", "chat", "", null, undefined]) {
    expect(safeNext(bad)).toBe("/documents");
  }
});

test("upload cap is 4 MiB and the message states it", () => {
  expect(MAX_UPLOAD_BYTES).toBe(4194304);
  expect(uploadTooLargeMessage(5 * 1024 * 1024)).toContain("5.0 MB");
});
