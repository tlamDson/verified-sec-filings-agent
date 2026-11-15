"""Filing text index: 10-K and 10-Q HTML to sections to chunks, each tagged with index_version.

Flow: `submissions` lists the filings, `enqueue` puts one `filing.sections` job per filing on
the queue, and the `handler` fetches the primary document through `EdgarClient`, runs
`pipeline.index_filing` (HTML to text blocks, blocks to sections, sections to chunks), and
writes the result with `store.PostgresChunkStore`.
"""
