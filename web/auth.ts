// Auth.js (next-auth) for this app. Sessions live in a signed, encrypted cookie: there is
// no user table. Real users sign in with an OAuth provider; the simulated cohort signs in
// with the credentials provider of `lib/auth/simulated`, which is off unless
// `SIM_LOGIN_SECRET` is set. Server only.

import type { NextAuthOptions } from "next-auth";
import { getServerSession } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import GitHubProvider from "next-auth/providers/github";
import GoogleProvider from "next-auth/providers/google";
import {
  type ApiIdentity,
  identityOf,
  oauthProviders,
  SIMULATED_PROVIDER,
} from "@/lib/auth/identity";
import { simulatedUser } from "@/lib/auth/simulated";

type Env = Record<string, string | undefined>;

function providers(env: Env): NextAuthOptions["providers"] {
  const configured: NextAuthOptions["providers"] = oauthProviders(env).map((provider) =>
    provider.id === "github" ? GitHubProvider(provider) : GoogleProvider(provider),
  );
  if ((env.SIM_LOGIN_SECRET ?? "").trim() !== "") {
    configured.push(
      CredentialsProvider({
        id: SIMULATED_PROVIDER,
        name: "Simulated test account",
        credentials: { email: { type: "email" }, password: { type: "password" } },
        authorize: async (credentials) =>
          simulatedUser(
            credentials?.email ?? "",
            credentials?.password ?? "",
            env.SIM_LOGIN_SECRET,
          ),
      }),
    );
  }
  return configured;
}

export function authOptions(env: Env = process.env): NextAuthOptions {
  return {
    providers: providers(env),
    session: { strategy: "jwt" },
    pages: { signIn: "/", error: "/" },
    callbacks: {
      signIn: ({ account }) => account !== null && identityOf(account) !== null,
      jwt: ({ token, account }) => {
        const identity = account ? identityOf(account) : null;
        return identity ? { ...token, uid: identity.id, cohort: identity.cohort } : token;
      },
      session: ({ session, token }) => ({
        ...session,
        identity: token.uid && token.cohort ? { id: token.uid, cohort: token.cohort } : null,
      }),
    },
  };
}

/** The API identity of the visitor, or null when they are not signed in. */
export async function currentIdentity(): Promise<ApiIdentity | null> {
  const session = await getServerSession(authOptions());
  return session?.identity ?? null;
}
