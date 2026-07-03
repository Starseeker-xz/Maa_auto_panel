# Session 2026-07-02_2144-manual-stop-delay

## Task

Investigate why the latest manual WebUI run took nearly a minute to actually stop after the user clicked stop, apparently while stuck around the MaaCore "已连接" / connected step. Try to reproduce with a manual run and determine whether the issue is in Linux_maa framework code or underlying maa-cli/MaaCore behavior.

## Session Notes

- Confirmed startup state loaded from global lessons, global memory index, project history, project lessons, and conversation index.
- Active session scratch directory: `.codex/conversations/2026-07-02_2144-manual-stop-delay/scratch/`.

## Tests / Commands

- Reproduced cold ADB-server manual stop delay via Web API. Run `2636bb1ed39e`: POST `/api/runs` for `General`, slept 12 seconds, POST `/api/runs/2636bb1ed39e/stop`, then polled `/api/runs/current`. Stop request returned `stopping` at +12.007s; final `stopped` arrived at +62.114s with return code 1. Raw poll summary: `scratch/cold-stop-repro.json`.
- Ran warm ADB-server comparison via Web API. Run `3f8150aa6912`: with local ADB server already listening on 127.0.0.1:5037, POST `/api/runs` for `General`, slept 5 seconds, POST `/api/runs/3f8150aa6912/stop`, and polled current state. Stop request returned `stopping` at +5.009s; final `stopped` arrived at +5.513s. Raw poll summary: `scratch/warm-stop-repro.json`.
- Searched MaaCore logs for `timeout when reading the output` and `Call \` adb devices \``. All three relevant manual stopped runs (`e87fa44a4cee`, `3af525bb11ac`, `2636bb1ed39e`) had `adb devices` cost `60001 ms`; warm comparison `3f8150aa6912` had cost `0 ms`.

## Findings

- Confirmed: Latest user-visible run `e87fa44a4cee` started at 21:35:56, stop requested at 21:36:15, and finished at 21:37:01.
- Confirmed: Later manual run `3af525bb11ac` started at 21:41:23, stop requested at 21:41:49, and finished at 21:42:24.
- Confirmed: Both delayed manual stops, plus reproduced run `2636bb1ed39e`, show the same MaaCore pattern: adb-lite first fails to contact local ADB server on 127.0.0.1:5037, MaaCore falls back to NativeIO, `adb devices` is waited for 60001 ms, then `adb connect 192.168.5.151:5555` succeeds and `Connected` is emitted. The prior stop request is only reflected after this connect phase finishes.
- Confirmed: In the warm comparison run `3f8150aa6912`, MaaCore's `adb devices` cost was 0 ms, `async_connect` took 551 ms, and manual stop finalized about 0.5 seconds after the stop request.
- Confirmed: Framework stop endpoint records and returns promptly; the backend status stays `stopping` because the child `maa-cli` process keeps running inside MaaCore connect code.
- Confirmed: `config/maa/profiles/default.toml` currently has `adb_lite_enabled = true` and `kill_adb_on_exit = true`; `config/linux-maa/schedules/daily-test.toml` has `adb_lite_enabled = false` but also `kill_adb_on_exit = true`.
- Confirmed: Older scheduled MaaCore logs also contain the same `adb devices` `60001 ms` cold-start delay, including runs with schedule profile `adb_lite_enabled = false`. Therefore disabling adb-lite alone is not sufficient.
- Likely: The root condition for the 60-second stall is a cold/missing local ADB server, combined with MaaCore's 60-second read timeout around `adb devices`. `kill_adb_on_exit = true` makes this recur by killing the local ADB server after each maa-cli exit.
- Likely: This is primarily MaaCore/ADB runtime behavior, but Linux_maa can mitigate it by keeping/prestarting ADB server before maa-cli runs and by making manual stop use the same terminate-then-kill fallback that scheduled runs already use through `run_maa_cli_process(should_stop=...)`.
- Session mistake: A log-search command used a double-quoted rg pattern containing backticks. Bash performed command substitution and ran `adb devices`, which started an ADB server. Use single quotes or `rg -e` for literal backticks.

## Environment Effects

- Created this session directory and session notes file.
- Generated manual run logs/state for reproduced run `2636bb1ed39e`.
- Generated manual run logs/state for warm comparison run `3f8150aa6912`.
- Accidentally started local ADB server by command-substitution mistake while searching logs. The later warm comparison maa-cli run exited with `kill_adb_on_exit = true`, and afterward `pgrep -a adb` plus `ss -H -ltn sport = :5037` showed no active ADB server/listener, so the accidental active effect is no longer present.
