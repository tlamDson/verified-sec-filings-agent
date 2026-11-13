// Today's usage of the signed-in user, read from the API when the page is rendered.

import type { ApiIdentity } from "@/lib/auth/identity";
import type { Usage } from "@/lib/chat/types";
import { forwardToApi } from "./proxy";

/** The usage the API reports, or null when the API cannot be asked right now. */
export async function currentUsage(
  identity: ApiIdentity,
  env: Record<string, string | undefined>,
): Promise<Usage | null> {
  const response = await forwardToApi({ identity, path: "/v1/me", method: "GET", env });
  if (!response.ok) {
    return null;
  }
  try {
    const body = (await response.json()) as { usage?: Usage };
    return body.usage ?? null;
  } catch {
    return null;
  }
}
