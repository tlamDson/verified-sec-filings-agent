import { currentIdentity } from "@/auth";
import { ChatApp } from "@/components/ChatApp";
import { SignInGate } from "@/components/SignInGate";
import { currentUsage } from "@/lib/api/usage";
import { signInChoices } from "@/lib/auth/identity";

export const dynamic = "force-dynamic";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const identity = await currentIdentity();
  if (identity === null) {
    const { error } = await searchParams; // set by Auth.js when a sign-in attempt failed
    return <SignInGate choices={signInChoices(process.env)} failed={error !== undefined} />;
  }
  return <ChatApp cohort={identity.cohort} usage={await currentUsage(identity, process.env)} />;
}
