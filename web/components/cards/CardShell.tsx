import type { ReactNode } from "react";
import type { FilingSource } from "@/lib/chat/types";
import { isSecUrl } from "@/lib/format";

/** The frame every card shares: what the figure is, whose it is, and for which period. */
export function CardShell({
  title,
  subject,
  period,
  children,
}: {
  title: string;
  subject: string;
  period: string;
  children: ReactNode;
}) {
  return (
    <article
      aria-label={`${title}, ${subject}, ${period}`}
      className="rounded-lg border border-neutral-200 bg-white p-4 text-sm shadow-sm dark:border-neutral-800 dark:bg-neutral-900"
    >
      <header className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3">
        <h4 className="font-medium">{title}</h4>
        <p className="text-xs text-neutral-500">
          {subject} · {period}
        </p>
      </header>
      {children}
    </article>
  );
}

/** A link to a filing on sec.gov; plain text when the address is anything else. */
export function FilingLink({ source }: { source: FilingSource }) {
  const label = `${source.form} filed ${source.filed}`;
  if (!isSecUrl(source.url)) {
    return <span>{label}</span>;
  }
  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      className="underline decoration-neutral-400 underline-offset-2 hover:decoration-current"
    >
      {label}
    </a>
  );
}

export function Missing({ children }: { children: ReactNode }) {
  return <p className="text-neutral-500">{children}</p>;
}
