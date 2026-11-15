// Who a signed-in account is to the API: an id and a cohort. An account from an OAuth
// provider is `real`; an account from the simulated sign-in is `simulated` and its id
// starts "sim:". The two never mix: the API refuses a token where they disagree.

import type { Cohort } from "@/lib/chat/types";

export interface ApiIdentity {
  id: string;
  cohort: Cohort;
}

export interface SignInChoice {
  id: string;
  name: string;
  cohort: Cohort;
}

export const SIMULATED_PROVIDER = "simulated";
const SIMULATED_PREFIX = "sim:";

const OAUTH_PROVIDERS = [
  { id: "github", name: "GitHub", idVar: "AUTH_GITHUB_ID", secretVar: "AUTH_GITHUB_SECRET" },
  { id: "google", name: "Google", idVar: "AUTH_GOOGLE_ID", secretVar: "AUTH_GOOGLE_SECRET" },
] as const;

type Env = Record<string, string | undefined>;

function isSet(value: string | undefined): value is string {
  return value !== undefined && value.trim() !== "";
}

/** The OAuth providers that have both their client id and secret, with those values. */
export function oauthProviders(env: Env) {
  return OAUTH_PROVIDERS.flatMap((provider) => {
    const clientId = env[provider.idVar];
    const clientSecret = env[provider.secretVar];
    return isSet(clientId) && isSet(clientSecret)
      ? [{ id: provider.id, name: provider.name, clientId, clientSecret }]
      : [];
  });
}

/** The ways to sign in that this deployment has configured, in the order shown. */
export function signInChoices(env: Env): SignInChoice[] {
  const choices: SignInChoice[] = oauthProviders(env).map(({ id, name }) => ({
    id,
    name,
    cohort: "real",
  }));
  if (isSet(env.SIM_LOGIN_SECRET)) {
    choices.push({ id: SIMULATED_PROVIDER, name: "Simulated test account", cohort: "simulated" });
  }
  return choices;
}

/** The API identity of an account, or null when the account cannot be one. */
export function identityOf(account: {
  provider: string;
  providerAccountId: string;
}): ApiIdentity | null {
  const { provider, providerAccountId } = account;
  if (provider === SIMULATED_PROVIDER) {
    return providerAccountId.startsWith(SIMULATED_PREFIX)
      ? { id: providerAccountId, cohort: "simulated" }
      : null;
  }
  if (!OAUTH_PROVIDERS.some((known) => known.id === provider) || providerAccountId === "") {
    return null;
  }
  return { id: `${provider}:${providerAccountId}`, cohort: "real" };
}
