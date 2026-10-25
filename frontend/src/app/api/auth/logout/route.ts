import { NextRequest } from "next/server";
import { handleLogout } from "@/lib/server/auth-handlers";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  return handleLogout(req);
}
