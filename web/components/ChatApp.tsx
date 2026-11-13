"use client";

import { signOut } from "next-auth/react";
import { useState } from "react";
import { sendFeedback, sendQuestion } from "@/lib/chat/send";
import type { Cohort, Usage } from "@/lib/chat/types";
import { Chat } from "./Chat";

/** The chat, connected to this app's routes. Each page load starts a new conversation. */
export function ChatApp({ cohort, usage }: { cohort: Cohort; usage: Usage | null }) {
  const [threadId] = useState(() => crypto.randomUUID());
  return (
    <Chat
      threadId={threadId}
      cohort={cohort}
      initialUsage={usage}
      send={sendQuestion}
      rate={sendFeedback}
      onSignOut={() => {
        void signOut({ callbackUrl: "/" });
      }}
    />
  );
}
