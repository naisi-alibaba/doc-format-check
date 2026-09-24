# Changelog

## 2.0.0

- Use pinned UTR59-r1 spacing classifications and Unicode16 grapheme boundaries by default. `--spacing-engine legacy` selects the old spacing policy.
- Bundle uniseg 0.10.0; no pip install or network calls at runtime.
- Fix known cross-word false positives in 定单 checks and explicit replacements.
- Always emit UTF-8 CLI output, including errors.
- Require `--report` outside the scan root for `--fix`; refuse to replace an existing installation.
- Preserve Markdown protected regions, BOM/CRLF and hard breaks; validate the batch before writing.
