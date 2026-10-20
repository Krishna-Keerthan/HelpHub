import type { NextRequest } from "next/server";
import { passthrough } from "@/lib/server/passthrough";

export const runtime = "nodejs";
export const maxDuration = 300;

type Ctx = { params: Promise<{ path: string[] }> };

const handle = async (req: NextRequest, ctx: Ctx) => passthrough(req, (await ctx.params).path);

export const GET = handle;
export const POST = handle;
export const DELETE = handle;
