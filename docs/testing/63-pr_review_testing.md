# Testing: PR Review (Plan 63)

## Test Files

| File | Tests | Coverage |
|------|-------|----------|
| `tests/test_review_models.py` | 8 | Enums, dataclass construction, defaults, serialization |
| `tests/test_diff_parser.py` | 9 | Unified diff parsing, language detection, generated files, renames, GitHub files API |
| `tests/test_review_github.py` | 5 | GitHub provider (mocked httpx): get PR, diff, files, post review, multiline comments |
| `tests/test_review_pipeline.py` | 8 | Budget files, JSON extraction, findings parsing, confidence filter, full pipeline (mocked LLM) |
| `tests/test_review_formatter.py` | 5 | WhatsApp summary format, GitHub comment format, severity/risk emojis |
| `tests/test_repo_analyzer.py` | 13 | Framework/linter/test runner detection, convention extraction, full analyze |
| `tests/test_repo_profile_crud.py` | 6 | SQLite CRUD: save, get, list, delete, upsert |
| `tests/test_symbol_extractor.py` | 8 | Python/JS/Go symbol extraction, imports, types, dedup, filtering |
| `tests/test_code_search.py` | 8 | Classify matches, read context, find refs/defs/tests, cross-file context |
| `tests/test_repo_clone.py` | 6 | Clone dir naming, get/remove clone, cleanup stale |

## Running

```bash
python3 -m pytest tests/test_review_*.py tests/test_diff_parser.py tests/test_repo_*.py tests/test_symbol_extractor.py tests/test_code_search.py -v
```

## Plan 64 Files (Hardening)

| File | Coverage |
|------|----------|
| `app/reviews/prompts.py` | Centralized prompts (REVIEW_SYSTEM, SUMMARY_SYSTEM, VERIFY_SYSTEM) |
| `app/reviews/verifier.py` | Multi-pass verification (verify_finding, verify_findings) |
| `scripts/pr_review_eval_cases.py` | 50 synthetic eval diffs |

## Eval Testing

```bash
# Seed the PR review eval cases
python3 scripts/seed_eval_dataset.py --section pr_review_security
python3 scripts/seed_eval_dataset.py --section pr_review_bugs
python3 scripts/seed_eval_dataset.py --section pr_review_clean

# Run PR review eval
make eval-pr-review
```

## Manual Testing

1. Set `GITHUB_TOKEN` in `.env`
2. `/pr-setup https://github.com/owner/repo` — verify repo profile created
3. `/pr-setup https://github.com/owner/repo --deep` — verify clone created
4. `/pr-review https://github.com/owner/repo/pull/123` — verify WhatsApp summary + GitHub comments
5. Verify deep reviews include cross-file context (definitions, usages, tests)
6. Test `--summary-only` flag (no GitHub comments posted)
