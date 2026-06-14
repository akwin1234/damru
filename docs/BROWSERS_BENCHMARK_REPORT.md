# Browsers Benchmark Report

This report records a Damru run against the external stealth benchmark project:

https://github.com/techinz/browsers-benchmark

Credit: the benchmark target definitions, checker structure, and report shape come from `techinz/browsers-benchmark`. Damru's code in this repository only provides a Redroid/Android adapter that plugs Damru into that upstream benchmark harness.

Adapter code used for Damru Redroid runs:

[../scripts/run_browsers_benchmark_damru.py](../scripts/run_browsers_benchmark_damru.py)

The benchmark was run with Damru Redroid on WSL2 using Android 14 runtime, random premium profiles per target, and a rotating residential SOCKS5 proxy (USA exit). Proxy credentials, local paths, local usernames, and IP addresses are intentionally excluded from this report.

## Result

Final bypass score: **10 / 10**

Final bypass rate: **100%**

Sanitized machine-readable result: [assets/benchmark/browsers-benchmark-final-clean.json](assets/benchmark/browsers-benchmark-final-clean.json)

| Target | Site | Result |
| --- | --- | --- |
| Google Search | `https://www.google.com/search?q=what+is+my+user+agent` | Pass |
| Cloudflare | `https://community.cloudflare.com` | Pass |
| DataDome | `https://datadome.co/customers-stories/` | Pass |
| DataDome / Hermès | `https://www.hermes.com/` | Pass |
| Amazon | `https://a.co/d/21FTKNR` | Pass |
| Ticketmaster / Imperva | `https://www.ticketmaster.com/` | Pass |
| Akamai Bot Manager | `https://www.mrporter.com` | Pass |
| PerimeterX / HUMAN | `https://www.priceline.com` | Pass |
| Kasada | `https://www.wizzair.com` | Pass |
| Reddit | `https://www.reddit.com/` | Pass |

## Browser Data

| Check | Result |
| --- | --- |
| CreepJS | Completed without benchmark error |
| Sannysoft plugins | Android-correct empty `PluginArray` / empty `MimeTypeArray`; the legacy desktop plugin row is treated as a false positive only after those live invariants are verified |
| WebRTC candidate IP | Returns spoofed proxy IP (default), or empty list `[]` when `webrtc_block=True` is enabled. |
| IP check | Completed through the configured residential proxy; exit IP redacted |

## reCAPTCHA Note

The benchmark project's `recaptcha_score` target is not included in the proxy bypass score. reCAPTCHA v3 scores are strongly affected by proxy reputation, recent refresh frequency, and Google-side rate limiting. A direct/no-proxy antcpt score can be captured separately for proof, but any screenshot must redact the visible IP address before publishing.

In the final proxy benchmark report above, reCAPTCHA was skipped rather than counted as a Damru browser failure.

Manual UI proof: separate antcpt checks run through the Damru UI returned **reCAPTCHA v3 score 0.9** in both direct and proxy modes. Any published screenshot must redact the visible IP address.

We tried automating this target repeatedly, but automated score extraction was unreliable because the page can remain in a detecting/error state after proxy reputation changes, repeated refreshes, or Google-side rate limits. The manual UI result is therefore recorded separately from the automated benchmark score.

## Stability Fixes From This Run

- DataImpulse-style rotating proxy URLs are normalized into a sticky session at Damru browser-session startup, so GeoIP, Android proxy bridge, and Chrome use the same exit during that session.
- Sticky sessions are no longer cached for the whole Python process. A new Damru browser session gets a new sticky session, which avoids repeatedly reusing a bad proxy exit.
- Random profile selection now respects the real Android runtime version, preventing Android 15 profiles from being selected on an Android 14 Redroid runtime.

## Repro Shape

The final proof run used the external benchmark adapter with:

```powershell
$env:DAMRU_BENCH_DEVICE='Samsung Galaxy S23'
$env:DAMRU_REPO='C:\path\to\damru'
python C:\path\to\damru\scripts\run_browsers_benchmark_damru.py
```

Use a valid residential proxy in `DAMRU_BENCH_PROXY` for proxy-mode testing. Do not commit proxy credentials or raw screenshots that expose IP addresses or site challenge tokens.
