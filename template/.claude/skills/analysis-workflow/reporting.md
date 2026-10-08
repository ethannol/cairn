# Reporting

- Every figure in `report.tmpl.md` is a `{{ledger.key}}` or `{{ledger.key:.2f}}`.
  `cairn verify` rejects unresolved keys and warns on bare numbers in prose.
- The first paragraph states the question, the population, and the answer with its
  uncertainty. Caveats go next to the claim they affect, not in an appendix.
- State the unit of analysis and the n at that level (wells, not samples; customers, not
  events).
- Exploratory findings get their own section and are labelled as such.
- Abstentions are written as results: what was asked, why the data cannot answer it, and
  the strongest claim that is supported.
- Figures: axis labels with units, the n, and the censoring convention in the caption.
- Do not edit `report.md`; it is rendered. Do not edit `artifacts/numbers.json`; it is
  produced by scripts.
