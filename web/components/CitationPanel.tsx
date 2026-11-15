import type { Citation } from "@/lib/chat/types";
import { isSecUrl, sectionLabel } from "@/lib/format";

function describe(citation: Citation): string {
  const parts = [`${citation.form}, filed ${citation.filing_date}`];
  if (citation.company !== null) {
    parts.unshift(citation.company.ticker);
  }
  if (citation.section !== null) {
    parts.push(sectionLabel(citation.section));
  }
  if (citation.report_date !== null) {
    parts.push(`period ended ${citation.report_date}`);
  }
  return parts.join(" · ");
}

/** The sources of one turn, numbered as the answer refers to them. */
export function CitationPanel({
  citations,
  active,
}: {
  citations: Citation[];
  active: string | null;
}) {
  return (
    <aside aria-label="Sources" className="text-sm">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-neutral-500">
        Sources
      </h2>
      {citations.length === 0 ? (
        <p className="text-neutral-500">No sources for this answer yet.</p>
      ) : (
        <ol className="space-y-3">
          {citations.map((citation, at) => (
            <li
              key={citation.key}
              aria-current={citation.key === active ? "true" : undefined}
              className="rounded-lg border border-neutral-200 p-3 aria-[current=true]:border-neutral-900 aria-[current=true]:bg-neutral-50 dark:border-neutral-800 dark:aria-[current=true]:border-neutral-200 dark:aria-[current=true]:bg-neutral-900"
            >
              <div className="flex items-baseline gap-2">
                <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-neutral-200 px-1 text-xs font-medium dark:bg-neutral-700">
                  {at + 1}
                </span>
                <p className="text-xs text-neutral-600 dark:text-neutral-400">
                  {describe(citation)}
                </p>
              </div>
              {citation.text !== null && (
                <blockquote className="mt-2 border-l-2 border-neutral-300 pl-3 leading-relaxed dark:border-neutral-700">
                  {citation.text}
                </blockquote>
              )}
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-neutral-500">
                <code className="break-all font-mono">{citation.key}</code>
                {isSecUrl(citation.url) && (
                  <a
                    href={citation.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline underline-offset-2"
                  >
                    Open on sec.gov
                  </a>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}
