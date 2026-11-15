"use client";

import { type FormEvent, useState } from "react";
import type { SignInChoice } from "@/lib/auth/identity";

export type SignIn = (
  provider: string,
  credentials: { email: string; password: string } | undefined,
) => void;

const INPUT =
  "w-full rounded-lg border border-neutral-300 bg-transparent p-2 text-sm dark:border-neutral-700";

function SimulatedForm({ choice, onSignIn }: { choice: SignInChoice; onSignIn: SignIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    onSignIn(choice.id, { email, password });
  }

  return (
    <form
      onSubmit={submit}
      className="space-y-2 rounded-lg border border-dashed border-neutral-300 p-4 dark:border-neutral-700"
    >
      <h2 className="text-sm font-medium">{choice.name}</h2>
      <p className="text-xs text-neutral-500">
        Simulated accounts are test traffic. They are labelled simulated and counted apart from real
        users.
      </p>
      <input
        aria-label="Simulated account email"
        type="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        placeholder="sim-01@example.com"
        className={INPUT}
      />
      <input
        aria-label="Simulated account password"
        type="password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        className={INPUT}
      />
      <button type="submit" className="rounded-lg border border-neutral-300 px-3 py-2 text-sm">
        Sign in as a simulated user
      </button>
    </form>
  );
}

/** What a visitor sees before signing in: the product, the ways in, and the disclaimer. */
export function SignInPanel({
  choices,
  onSignIn,
  failed = false,
}: {
  choices: SignInChoice[];
  onSignIn: SignIn;
  /** The last attempt to sign in did not succeed. */
  failed?: boolean;
}) {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-5 px-4">
      <h1 className="text-3xl font-semibold">Verified SEC Filings Research Agent</h1>
      <p>
        Ask about public 10-K and 10-Q filings. Every number in an answer is traced to an XBRL fact
        or a cited passage.
      </p>
      {choices.length === 0 && (
        <p className="text-sm text-neutral-500">Sign-in is not configured for this deployment.</p>
      )}
      {failed && (
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          Sign-in did not succeed. Check the account and try again.
        </p>
      )}
      {choices.map((choice) =>
        choice.cohort === "simulated" ? (
          <SimulatedForm key={choice.id} choice={choice} onSignIn={onSignIn} />
        ) : (
          <button
            key={choice.id}
            type="button"
            onClick={() => onSignIn(choice.id, undefined)}
            className="rounded-lg bg-neutral-900 px-4 py-3 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
          >
            Continue with {choice.name}
          </button>
        ),
      )}
      <p className="text-sm opacity-70">Not investment advice.</p>
    </main>
  );
}
