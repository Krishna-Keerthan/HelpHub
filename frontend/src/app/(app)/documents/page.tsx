import type { Metadata } from "next";
import { DocumentsView } from "@/components/DocumentsView";

export const metadata: Metadata = {
  title: "Documents",
  description: "Upload, list and delete the support documents your answers are built from.",
};

export default function DocumentsPage() {
  return <DocumentsView />;
}
