# AirNode Launch Plan

Goal: ~$50 in sales. Target: $3–$5 one-time (pay-what-you-want, $3 suggested). Keep 14-day trial.

## Prerelease
- [ ] `git tag v1.0.0 && git push --tags` → CI builds + GitHub Release (exe, sha256, Setup.exe)
- [ ] Smoke-test install → PIN → phone QR connect → video stream
- [ ] 2–3 screenshots + 30s phone-streaming video
- [ ] Plain-English release notes (3–5 bullets)

## Distribution (free download → pay for license)
- GitHub Releases: free exe/installer
- License keys via Gumroad (best for Zambia) or Lemonsqueezy
- Link "Support AirNode — get a license key" in README, Settings License card, tray menu
- Pre-generate keys with `AirNode.exe --generate-key`

## Launch day (days 1–3) — post everywhere same day, title the problem not product
- Reddit: r/selfhosted, r/software, r/Windows (if wanted)
- Product Hunt: "no cloud / works over hotspot / zero internet" angle; reply to all comments
- Hacker News Show HN: link GitHub, not store
- AlternativeTo: list under LocalSend/Snapdrop/KDE Connect/Snapdrop alternatives (long-tail win)

## Weeks 2–4
- Post "v1.0.1 added X" updates to communities that engaged
- Track downloads via GitHub Release stats; usage via update-check cache
- If stalled: improve story (phone-streaming demo), don't cut price

## Why not $1
| Price | Net per sale (~40% fees) | Sales for $50 |
|---|---|---|
| $1 | ~$0.45–$0.65 | 75–110 |
| $3 | ~$1.60–$1.80 | 28–32 |
| $5 | ~$2.60–$3.00 | 17–20 |

$1: processor fees eat half, signals "junk". $3–$5 = impulse buy but 5× fewer customers needed. Keep trial so users verify before paying.

## Bottom line
Distribution >> price. A good r/selfhosted post + Gumroad link beats $1 pricing. Ten enthusiastic users > hundred silent downloads.