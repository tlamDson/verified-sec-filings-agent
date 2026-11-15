# Filing fixtures (simulated)

Every file here is **simulated data**, written by hand for tests. No file was downloaded
from SEC, and no company, number, or sentence in them is real.

They copy the layout traits of real inline-XBRL 10-K and 10-Q documents that the parser
must handle:

- a hidden `ix:header` block (`display:none`) holding XBRL facts that must not become text;
- a table of contents whose rows repeat every item heading;
- headings in a `div`, split over two blocks, or laid out as table cells;
- non-breaking spaces, character references, curly apostrophes;
- page numbers and "Table of Contents" back-links at every page break;
- cross-references to other items inside body text;
- `Items 1 and 2.` combined headings.

| File                   | Simulates                                         |
| ---------------------- | ------------------------------------------------- |
| `sim-10k.htm`          | Annual report (Items 1, 1A, 7, 7A and the rest)   |
| `sim-10q.htm`          | Quarterly report (Part I and Part II)             |
| `sim-10ka-part3.htm`   | 10-K/A that only amends Part III (no text items)  |
| `sim-10k-ibr.htm`      | 10-K whose Items 1A, 7, 7A incorporate Exhibit 13 by reference |
| `sim-ex13.htm`         | Exhibit 13 annual report: no Item headings, running headers |
| `sim-filing-index.htm` | EDGAR `<accession>-index.htm` filing index page   |
| `sim-submissions.json` | `data.sec.gov/submissions` first page             |
| `sim-submissions-001.json` | An older `filings.files` page                 |
