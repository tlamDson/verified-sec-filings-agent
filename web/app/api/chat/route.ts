// One turn: the signed-in user's question goes to the API and its event stream comes back.

import { currentIdentity } from "@/auth";
import { forwardToApi } from "@/lib/api/proxy";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  return forwardToApi({
    identity: await currentIdentity(),
    path: "/v1/chat",
    method: "POST",
    body: await request.text(),
    env: process.env,
  });
}
