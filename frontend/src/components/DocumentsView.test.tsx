import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { routeFetch } from "@/test/fetch-mock";
import { DocumentsView } from "./DocumentsView";

const doc = (id: string, title: string, status = "READY") => ({
  id,
  title,
  status,
  error: null,
  created_by: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});

afterEach(() => vi.restoreAllMocks());

// The role lookup (GET /api/auth/me) is not what these tests are about.
const docKeys = (f: { keys: () => string[] }) => f.keys().filter((k) => k !== "GET /api/auth/me");

const pick = (file: File) =>
  fireEvent.change(screen.getByLabelText("Upload a document"), { target: { files: [file] } });

test("lists documents", async () => {
  routeFetch({ "GET /api/documents": () => Response.json([doc("1", "Refund policy"), doc("2", "Setup guide")]) });
  render(<DocumentsView />);
  expect(await screen.findByText("Refund policy")).toBeInTheDocument();
  expect(screen.getByText("Setup guide")).toBeInTheDocument();
  expect(screen.getByRole("list", { name: "Documents" })).toBeInTheDocument();
  expect(screen.getByLabelText("Upload a document")).toHaveAccessibleDescription(/Files up to 4 MB\. Plain-text documents are also capped at about 500,000 extracted characters\./);
});

test("a file over 4 MB is rejected client-side with a clear message and nothing is sent", async () => {
  const f = routeFetch({ "GET /api/documents": () => Response.json([]) });
  render(<DocumentsView />);
  await screen.findByText("No documents yet.");
  pick(new File([new Uint8Array(4 * 1024 * 1024 + 1)], "big.pdf", { type: "application/pdf" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("limited to 4 MB");
  expect(docKeys(f)).toEqual(["GET /api/documents"]);
});

test("exactly 4 MB is uploaded, then the list reloads", async () => {
  let listed = 0;
  const f = routeFetch({
    "GET /api/documents": () => Response.json(listed++ === 0 ? [] : [doc("1", "ok.pdf")]),
    "POST /api/documents/upload": () => Response.json(doc("1", "ok.pdf"), { status: 201 }),
  });
  render(<DocumentsView />);
  await screen.findByText("No documents yet.");
  pick(new File([new Uint8Array(4 * 1024 * 1024)], "ok.pdf", { type: "application/pdf" }));
  expect(await screen.findByText("ok.pdf")).toBeInTheDocument();
  expect(docKeys(f)).toEqual(["GET /api/documents", "POST /api/documents/upload", "GET /api/documents"]);
});

test("server 413 on upload shows the backend's message and both limits", async () => {
  routeFetch({
    "GET /api/documents": () => Response.json([]),
    "POST /api/documents/upload": () => Response.json({ detail: "Document is too large" }, { status: 413 }),
  });
  render(<DocumentsView />);
  await screen.findByText("No documents yet.");
  pick(new File(["x"], "long.txt"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Document is too large");
  expect(alert).toHaveTextContent("500,000 extracted characters");
});

test("server 415 on upload is explained", async () => {
  routeFetch({
    "GET /api/documents": () => Response.json([]),
    "POST /api/documents/upload": () => Response.json({}, { status: 415 }),
  });
  render(<DocumentsView />);
  await screen.findByText("No documents yet.");
  pick(new File(["x"], "a.exe"));
  expect(await screen.findByRole("alert")).toHaveTextContent("not supported");
});

test("delete asks for confirmation; cancel sends nothing, confirm deletes", async () => {
  const f = routeFetch({
    "GET /api/documents": () => Response.json([doc("1", "Refund policy")]),
    "DELETE /api/documents/1": () => new Response(null, { status: 204 }),
  });
  render(<DocumentsView />);
  const del = await screen.findByRole("button", { name: "Delete Refund policy" });

  vi.spyOn(window, "confirm").mockReturnValueOnce(false);
  fireEvent.click(del);
  expect(docKeys(f)).toEqual(["GET /api/documents"]);

  vi.spyOn(window, "confirm").mockReturnValueOnce(true);
  fireEvent.click(del);
  await waitFor(() => expect(screen.queryByText("Refund policy")).not.toBeInTheDocument());
  expect(f.keys()).toContain("DELETE /api/documents/1");
});

test("cold start (503) on load shows the waking message", async () => {
  routeFetch({ "GET /api/documents": () => Response.json({ code: "service_waking" }, { status: 503 }) });
  render(<DocumentsView />);
  expect(await screen.findByRole("alert")).toHaveTextContent("waking up");
});

test("loading state is announced politely, then replaced by the list", async () => {
  routeFetch({ "GET /api/documents": () => Response.json([doc("1", "A")]) });
  render(<DocumentsView />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading documents");
  expect(await screen.findByText("A")).toBeInTheDocument();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

test("empty state explains what to do", async () => {
  routeFetch({ "GET /api/documents": () => Response.json([]) });
  render(<DocumentsView />);
  expect(await screen.findByText("No documents yet.")).toBeInTheDocument();
  expect(screen.getByText(/Upload a file up to 4 MB/)).toBeInTheDocument();
});

test("a failed load shows an alert and Try again recovers", async () => {
  let n = 0;
  routeFetch({
    "GET /api/documents": () =>
      n++ === 0 ? Response.json({ code: "x" }, { status: 500 }) : Response.json([doc("1", "Back")]),
  });
  render(<DocumentsView />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("Back")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
});

test("a viewer sees no upload control and a read-only note", async () => {
  routeFetch({
    "GET /api/documents": () => Response.json([doc("1", "A")]),
    "GET /api/auth/me": () => Response.json({ id: "u", email: "v@x.co", role: "viewer" }),
  });
  render(<DocumentsView />);
  await screen.findByText("Read-only account: uploads are disabled.");
  expect(screen.queryByLabelText("Upload a document")).toBeNull();
});

test("an admin still sees the upload control", async () => {
  routeFetch({
    "GET /api/documents": () => Response.json([]),
    "GET /api/auth/me": () => Response.json({ id: "u", email: "a@x.co", role: "admin" }),
  });
  render(<DocumentsView />);
  await screen.findByText("No documents yet.");
  expect(screen.getByLabelText("Upload a document")).toBeInTheDocument();
});

test("a 403 on upload says the account is read-only", async () => {
  routeFetch({
    "GET /api/documents": () => Response.json([]),
    "POST /api/documents/upload": () => Response.json({ detail: "Forbidden" }, { status: 403 }),
  });
  render(<DocumentsView />);
  await screen.findByText("No documents yet.");
  pick(new File(["x"], "a.txt"));
  expect(await screen.findByRole("alert")).toHaveTextContent("read-only");
});
