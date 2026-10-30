import { cookies } from "next/headers";
import { HomePage, homeMetadata } from "@/components/home/HomePage";

// Same page as "/" but never redirects, so a signed-in user can come back to it from the app header.
export const dynamic = "force-dynamic";

export const metadata = homeMetadata;

export default async function HomeRoute() {
  return <HomePage signedIn={Boolean((await cookies()).get("hh_rt")?.value)} />;
}
