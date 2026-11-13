// What this app keeps in the Auth.js session: the API identity of the signed-in account.

import type { ApiIdentity } from "@/lib/auth/identity";
import type { Cohort } from "@/lib/chat/types";

declare module "next-auth" {
  interface Session {
    identity: ApiIdentity | null;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    uid?: string;
    cohort?: Cohort;
  }
}
