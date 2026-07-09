# ctxmem benchmark

_Reproducible measurement of what `ctxmem` feeds an AI agent versus the naive approach._

- **Repo under test:** `bench-django`
- **Tokenizer:** tiktoken/cl100k_base
- **Baseline (“without ctxmem”):** whole relevant source files, **test files excluded** (a real agent would not paste entire test suites to answer a question).
- **Queries:** 13

## Headline

| Metric | Without ctxmem | With ctxmem | Improvement |
|---|--:|--:|--:|
| Context tokens (total) | 272,354 | 14,028 | **19.4x smaller** (94.8%) |
| Premium requests (total) | 49 | 13 | **3.8x fewer** |

## Context tokens per question

![tokens](bench_tokens.svg)

## Premium requests per question

Premium requests are billed **per model round-trip**, not per token. Without stored memory an agent orients itself and then opens each relevant file (one round-trip each); `ctxmem` returns every snippet in a single `recall`.

![requests](bench_requests.svg)

## Full results

| Query | Tok without | Tok with | Saved | Requests w/o | Requests w/ |
|---|--:|--:|--:|--:|--:|
| how does the QuerySet class build and execute SQL | 67,303 | 1,398 | 97.9% | 7 | 1 |
| how does URL routing and the resolver match a request | 30,338 | 700 | 97.7% | 4 | 1 |
| how are model fields defined and validated | 25,160 | 1,311 | 94.8% | 4 | 1 |
| how does form validation and the clean method work | 7,625 | 1,388 | 81.8% | 3 | 1 |
| how does middleware process request and response | 1,812 | 871 | 51.9% | 3 | 1 |
| how is the User model and authentication implemented | 34,709 | 1,141 | 96.7% | 5 | 1 |
| how do database migrations apply operations | 1,646 | 1,031 | 37.4% | 2 | 1 |
| how does the signal dispatcher connect and send | 3,792 | 749 | 80.2% | 2 | 1 |
| how is the ORM manager attached to a model | 55,877 | 974 | 98.3% | 4 | 1 |
| how does the admin site register models | 736 | 1,265 | -71.9% | 2 | 1 |
| how does session middleware store data | 2,676 | 668 | 75.0% | 5 | 1 |
| how does the WSGI handler build a response | 5,819 | 1,271 | 78.2% | 5 | 1 |
| how does model form save create instances | 34,861 | 1,261 | 96.4% | 3 | 1 |
| **TOTAL** | **272,354** | **14,028** | **94.8%** | **49** | **13** |

## How to reproduce

```bash
ctxmem init && ctxmem sync            # index the repo
ctxmem bench --suite QUESTIONS.txt \
    --baseline files --report bench
```
