import type { Metadata } from "next";
import { CompareView } from "@/components/CompareView";

export const metadata: Metadata = {
  title: "Compare retrieval",
  description: "Run one query through vector, keyword and hybrid search and compare the passages each returns.",
};

export default function ComparePage() {
  return <CompareView />;
}
