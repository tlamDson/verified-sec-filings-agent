// A thumbs up or down on a turn the signed-in user asked.

import { currentIdentity } from "@/auth";
import { forwardToApi } from "@/lib/api/proxy";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  return forwardToApi({
    identity: await currentIdentity(),
    path: "/v1/feedback",
    method: "POST",
    body: await request.text(),
    env: process.env,
  });
}
