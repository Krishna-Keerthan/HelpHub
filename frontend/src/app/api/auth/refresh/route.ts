import { NextRequest } from "next/server";
import { handleRefresh } from "@/lib/server/auth-handlers";

export const runtime = "nodejs";
export const maxDuration = 300;

export async function POST(req: NextRequest) {
  return handleRefresh(req);
}
