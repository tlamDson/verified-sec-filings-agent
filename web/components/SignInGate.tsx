"use client";

import { signIn } from "next-auth/react";
import type { SignInChoice } from "@/lib/auth/identity";
import { SignInPanel } from "./SignInPanel";

/** The sign-in panel, connected to Auth.js. */
export function SignInGate({ choices, failed }: { choices: SignInChoice[]; failed: boolean }) {
  return (
    <SignInPanel
      choices={choices}
      failed={failed}
      onSignIn={(provider, credentials) => {
        void signIn(provider, { ...credentials, callbackUrl: "/" });
      }}
    />
  );
}
