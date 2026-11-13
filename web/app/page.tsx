export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 px-4">
      <h1 className="text-3xl font-semibold">Verified SEC Filings Research Agent</h1>
      <p>
        Ask about public 10-K and 10-Q filings. Every number in an answer is traced to an XBRL fact
        or a cited passage.
      </p>
      <p className="text-sm opacity-70">Not investment advice.</p>
    </main>
  );
}
