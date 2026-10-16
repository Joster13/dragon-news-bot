# Dragon News 2.0 — first digest editorial audit fixes (2026-10-16)

## Scope

Based on the 2026-10-16 first SHADOW digest screenshots, regression tests cover:

1. **Reprints across publishers**: narrowly anchor technology levies on electronics and P2P cryptocurrency ban stories with identical claimed effective dates. This deduplicates **claims** and does NOT verify their legal truth. Different dates, contrary legislative actions, or different legislative stages remain separate.
2. **Future-dated legal statements**: exclude sole-attributed, definitive future legal bans/effective dates when a primary normative status has not been established by the editor. This is a conservative risk gate, not an independent legal source verifier. A proposal remains a proposal; no wording is upgraded into enacted law.
3. **Entertainment**: reject fictional-series / television premiere headlines that are not substantive world/economy developments.
4. **Telegram cleanup**: remove only known navigation/subscription lines at the *end* of a post; use the first intact sentence for titles where possible, otherwise cut at a whole-word boundary and append an ellipsis.
5. **Regional drone warnings**: when a later, eligible Lipetsk BPLA all-clear is available within 12 hours, omit both the transient warning and routine all-clear from the morning digest. An editorially rejected/untrusted all-clear or an all-clear from another region must not suppress the warning. This is NOT real-time civil-defense guidance.

## Operational limits

- No schema migration or changes to production SQLite. No change to main.py, BotHost settings, Telegram polling, messages or AUTO_SEND.
- GitHub Actions uses synthetic and regression examples; successful unit tests do not prove 95% editorial precision or 85% recall against manually labeled real articles.
- The original SHADOW digest for **2026-10-16** is immutable. Updating code does **not** rewrite it. Future shadow digests will use the new rules only after a separately approved test-instance deployment.
- First-day case descriptions come from screenshots and are not independently fact-checked. Especially, no assertion is made that a P2P ban effective 1 July 2027 was enacted.
- Event matching remains heuristic. Different paraphrases can still remain separate; controversial legal and military claims should continue receiving human review.
- The heuristic title/footer cleanup applies to newly ingested posts; old SQLite rows are left unchanged.
- Operational 7-day measurement with 20 sources remains a separate task; record a stable window with the new editorial rules after test-only deployment.

## Verification

Run `python -m compileall -q .` and `python -m unittest discover -s tests -v`.

## Rollout instructions — separate SHADOW project ONLY

1. Keep the production Dragon News project and `main` Git branch untouched.
2. When authorized, change Git branch of **existing** test project Dragon News 2.0 SHADOW to `trial/dragon-news-v2-editorial-audit-20261016`.
3. Confirm Main File is exactly `shadow_runner.py`, not `main.py`.
4. Rebuild/restart **only SHADOW**, preserving `/app/data/dragon_news_shadow.sqlite3`, `-wal` and `-shm`; no recreation or cleanup of the instance.
5. In the SHADOW-only terminal run `python shadow_runner.py --status` and `python shadow_runner.py --sources`; source count should still be 20 and all articles retained. No semicolon commands needed.
6. Review future test digest via `python shadow_runner.py --preview-date YYYY-MM-DD` (replace date with an actual newly built day after rollout). Previously saved 2026-10-16 preview is not regenerated.
7. Validate a sample of actual selected news and report duplicates, trust misclassification and cut-off titles. Do not promote to production until acceptance criteria are separately met.

## Git tracking

- Development branch: `feature/dragon-news-v2-editorial-audit-20261016`.
- Draft PR: https://github.com/Joster13/dragon-news-bot/pull/8
