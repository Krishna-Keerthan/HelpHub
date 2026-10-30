import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { HomePage, homeMetadata } from "@/components/home/HomePage";

// Reads cookies and server env per request: the redirect and the demo button reflect the running configuration.
export const dynamic = "force-dynamic";

export const metadata = homeMetadata;

export default async function Home() {
  if ((await cookies()).get("hh_rt")?.value) redirect("/documents");
  return <HomePage signedIn={false} />;
}
