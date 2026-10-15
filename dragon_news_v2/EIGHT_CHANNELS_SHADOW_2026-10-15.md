# Dragon News 2.0 SHADOW — eight new public Telegram sources

## Scope and source identity

Added eight **public-only**, read-only Telegram channel sources:

| source_id | Public page | Editorial hint |
|---|---|---|
| cbpub | https://t.me/s/Cbpub | Russia (high noise; adverts/viral posts filtered) |
| cb_economics | https://t.me/s/cb_economics | Finance/crypto |
| lipetsktop1 | https://t.me/s/lipetsktop1 | Lipetsk region, urgent services/roads |
| exploitex | https://t.me/s/exploitex | VPN/internet and technology |
| vgtimes | https://t.me/s/vgtimes | PC gaming |
| naebnet | https://t.me/s/naebnet | Internet, finance, AI |
| denissexy | https://t.me/s/denissexy | IT/AI |
| habr_com_news | https://t.me/s/habr_com_news | IT/cybersecurity |

All twelve original sources remain in the registry, for a total of **20**. No paid Telegram API, webhook, bot token, or additional Telegram polling process is used.

## Editorial safety

- New channels use source-bound data-post validation to reject messages attributed to other handles by unexpected HTML.
- Explicit paid promotions (erid/ad markers, partner materials, promo-code offers), photo-only and trivial short captions are omitted. Short substantive local outage notices and security patches are retained.
- Other informational posts still pass through the existing editorial engine; collection does not imply inclusion.
- Only location-relevant service/road alerts from the curated Lipetsk source may receive the Lipetsk category without saying Lipetsk in the title. Headlines explicitly mentioning other cities are not forcibly classified as Lipetsk.
- A Telegram channel's claim is still an **attributed report**, not a verified fact. `single_attributed` remains the default without documented original corroboration.
- Habr RSS and @habr_com_news are conservatively grouped when there is a high-confidence same-event match; they are **never** automatically counted as two independent evidentiary origins. Ambiguous paraphrases may remain separate pending review.
- Filters are conservative heuristics. CI does **not** establish 95% editorial precision or 85% recall: a manually annotated real-world dataset is still required.

## Updating the existing SHADOW project on BotHost

Do not change the production BotHost project, GitHub main branch, Telegram token, AUTO_SEND or production SQLite.

1. Open **Dragon News 2.0 SHADOW** (the existing test instance). Do **not** create another project.
2. Set its Git branch to `trial/dragon-news-v2-eight-channels-20261015`, **only after the draft branch has passed GitHub Actions**.
3. Confirm the Main File remains `shadow_runner.py` (never `main.py`).
4. Confirm its persistent data path remains `/app/data/dragon_news_shadow.sqlite3`. Do not delete, overwrite, move, copy, reset or migrate that file or the WAL/SHM files. No storage cleanup.
5. Save and update **only SHADOW** from Git; restarting the test process is sufficient. There is no change to database schema.
6. In the test-only terminal run the following commands individually (no semicolon characters):

    python shadow_runner.py --status

    python shadow_runner.py --sources

7. Verify that all eight new source IDs have kind=public_telegram and their configured URLs. After an actual collection cycle, confirm for each: `last_error=null`, `last_success_at` updated, **and** `article_count > 0`. A successful HTTP response without parsed posts is not sufficient to claim live source coverage.
8. Ensure the original twelve sources remain. Total expected source rows: **20** after first post-deploy collection.
9. Existing article rows, source history, audit decisions and previously saved test digests remain. Do not regenerate historical digests to force new categories.

## Monitoring and trial continuity

These changes expand the observation set in the middle of an existing trial. Preserve earlier data, but assess the new **20-source configuration** over seven *complete daily digests* after the updated collector was activated. Pre-upgrade partial cycles are historical diagnostics, not evidence that the 20-source configuration worked.

The `--sources` report now returns read-only `article_count` and `last_article_fetched_at` alongside the previous source status. If any channel fails, record the source_id and last_error, and review only the SHADOW logs. Do not switch the working bot.

## Offline verification

`python -m unittest discover -s tests -v`

The test suite covers all eight sources, no loss of the original sources, source-bound Telegram post IDs, obvious promo/noise suppression, local source attribution, exact same-event duplicate handling, preservation of existing SQLite rows, and report metrics. BotHost-specific reachability remains to be measured on the actual test deployment.
