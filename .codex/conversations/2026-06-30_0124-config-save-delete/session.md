# Session 2026-06-30_0124-config-save-delete

## Scope

- Implement frontend config persistence to backend.
- Add main-page save/reset buttons that appear after local config edits and confirm before acting.
- Add delete-current-config action near the add-config button, confirming first and moving deleted config files to a recycle/trash folder.
- Extract reusable deletion/trash logic for future reuse.
- Investigate and fix asymmetric right spacing in the left pane.
- Before implementation, review relevant frontend/backend code and project documentation for unreasonable coupling, redundancy, and architecture issues.

## Initial State

- Confirmed: Loaded `/root/.codex/lessons.md`, `/root/.codex/memories/index.md`, `.codex/project-history.md`, `.codex/project-lessons.md`, and `.codex/conversations/index.md`.
- Confirmed: Worktree had an existing untracked `.codex/conversations/2026-06-29_2232-config-editing/scratch/maa-src/` directory before this session; leave it untouched.

## Running Notes

- Confirmed: Reviewed project-owned docs: `README.md`, `docs/README.md`, `docs/maa-runtime.md`, `docs/architecture-direction.md`, `docs/maa-reading-notes.md`, and relevant maa-cli config/schema docs.
- Confirmed: Reviewed frontend/backend config paths, including `MainPage`, `TaskListPane`, `ConfigEditorPane`, task workspace helpers, API helpers, `ConfigManager`, config schema validation, FastAPI app, and maa-cli runner metadata stripping.
- Confirmed: Added dependency `tomli-w>=1.2.0` through `uv add tomli-w`; this updated `pyproject.toml`, `uv.lock`, and the active `.venv`.
- Confirmed: Backend config save now lives in `ConfigManager.write_task_config`; FastAPI exposes `PUT /api/configs/tasks/{name}`.
- Confirmed: Backend config deletion now moves files through reusable `TrashManager` into `config/maa/.trash/`; FastAPI exposes `DELETE /api/configs/{kind}/{name}`.
- Confirmed: Frontend now stages edits as per-config drafts and shows save/reset controls at the bottom right of the main page after staged changes.
- Confirmed: Frontend delete-current-config control was added next to the add-config button and uses the shared confirmation dialog.
- Confirmed: Left-pane extra right padding came from repeated `pr-2` on header/list/footer sections; removed those asymmetric paddings.
- Confirmed: Fixed `create_app(repo_root)` so an explicit root is honored directly instead of being passed through `find_repo_root`.
- Confirmed: Fixed route lock after user report. `MainPage` now derives the selected task config from the URL instead of keeping a second local `taskConfig` state and `initialTaskConfig` ref. The config-list load effect no longer navigates back to the initial config.
- Confirmed: Task rows are now clickable across the whole row to open the child editor; checkbox/buttons/drag handle remain independent controls.
- Confirmed: User changed settings-page direction from tabbed/subpage switching to parallel same-screen display because web space is sufficient.
- Confirmed: Reviewed maa-cli docs under `docs/maa-upstream/zh-cn/manual/cli/` plus local `docs/maa-cli/schemas/{cli,asst}.schema.json` before implementing settings.
- Confirmed: Added framework settings manager for `config/linux-maa/settings.toml`; defaults include timezone mode `auto`, manual timezone `UTC`, game-day offset `4`, scheduler disabled, theme mode `system`, and theme color `cyan`.
- Confirmed: Framework timezone resolution supports backend-local auto mode, fixed offsets like `UTC+04:00`, and IANA timezone names such as `Europe/London`; IANA resolution accounts for current DST offset at save/use time.
- Confirmed: Added `GET/PUT /api/settings` for framework settings, default Profile, and maa-cli config. Maa profile/cli payloads are validated before writing.
- Confirmed: Added reusable maintenance action manager and API. It now distinguishes `core-update` (`maa update`), `resource-update` (`maa hot-update`), and `cli-update` (`maa self update`).
- Confirmed: Settings page now shows framework/timezone, default Profile, maa-cli/resource controls, maintenance output, and theme controls in parallel panels instead of tabbed pages.
- Confirmed: Save/reset confirmation logic is now extracted into `frontend/src/components/DirtyActions.tsx` and reused by main page and settings page.
- Confirmed: WebUI public start-run payload no longer exposes `attempts` or `timeout_seconds`; the CLI wrapper still keeps its separate command-line retry/timeout flags.
- Confirmed: Task item ids now normalize to readable ids with stable hash suffixes when read from backend; newly created frontend task items use a random 8-hex suffix before backend normalization.
- Confirmed: Theme colors now route through CSS variables; hard-coded cyan active/start colors were replaced by primary/accent variables.
- Confirmed: Left-pane row active state and action column were tightened to reduce the prior right-heavy visual spacing.
- Confirmed: User clarified that "game day offset" was only an example and must not be a user setting. Removed it from the settings UI and backend merged settings response.
- Confirmed: Settings timezone now offers backend-auto, browser timezone, and manual timezone modes. Browser timezone uses `Intl.DateTimeFormat().resolvedOptions().timeZone`; manual mode is still resolved by backend `zoneinfo`, so IANA names handle DST.
- Confirmed: Settings UI warns when backend/container timezone and browser timezone differ and offers a "use browser timezone" action. It does not attempt to change host/container time.
- Confirmed: MAA GUI "software update" vs "resource update" was checked in local GUI source. GUI software update handles MAA program/Core package versions; GUI resource update updates resource data such as new stages, drop icons, and recruitment tags.
- Confirmed: maa-cli update concepts are split into three actions here:
  - `core-update`: `maa update --batch`, updates MaaCore and bundled/base resources when Core version is newer.
  - `resource-update`: `maa hot-update --batch`, updates hot-updateable MaaResource git content; it does not update base resources.
  - `cli-update`: `maa self update --batch`, updates maa-cli binary.
- Confirmed: Added update-info API/UI so users can inspect local and remote versions/commits before confirming an update.
- Confirmed: Theme changes now apply immediately and persist in browser localStorage; theme no longer contributes to the settings page dirty/save state.
- Confirmed: Returning to the main page from schedule/settings now uses localStorage `linux-maa:last-main-path`, preserving the last task config/item route when using the sidebar home button.

## Tests

- `uv run python -m compileall -q src`: passed.
- `npm run build` in `frontend/`: passed; Vite reported only the existing large chunk warning.
- Backend manager scratch save/delete test: passed, wrote `daily.toml`, read task item state back, moved deleted file into scratch `config/maa/.trash/`.
- Real FastAPI scratch server on `127.0.0.1:8765`: `PUT /api/configs/tasks/daily`, `GET /api/configs/tasks/daily`, and `DELETE /api/configs/tasks/daily` all passed after fixing explicit repo-root handling; server was stopped afterward.
- `fastapi.testclient.TestClient` was not usable because this environment still lacks `httpx2`, matching existing project lesson.
- Started real WebUI with `uv run linux-maa webui --host 0.0.0.0 --port 8000`; `curl /` returned `200 text/html`, and `curl /api/configs` returned the config listing.
- After route-lock fix, `npm run build` passed again and `curl /` from the running 8000 service returned the new `index-TUv12d1E.js` bundle.
- `uv run python -m compileall -q src`: passed again after settings backend work.
- `npm run build` in `frontend/`: passed after settings page/theme work; Vite reported only the existing large chunk warning. Latest built bundle is `index-B1xBB_jy.js` with CSS `index-Dnv7PgSs.css`.
- Real 8000 service checks after restart:
  - `GET /api/settings`: passed, returned valid profile/cli validation and UTC backend timezone in this environment.
  - `GET /api/configs/tasks/test`: passed, returned normalized first task id `startup-a5ce8dac`.
  - `GET /openapi.json`: passed, `StartRunPayload` contains only `task`, `profile`, and `log_level`.
  - `GET /settings`: passed, served the new built frontend assets.
- Temporary-directory direct settings write test: passed without touching project config. `Europe/London` resolved to `UTC+01:00` on 2026-06-30, and temporary `settings.toml`/`cli.toml` were written.
- `npm run build` in `frontend/`: passed after timezone/update-info/theme-route changes. Latest built bundle is `index-C_DhaW-w.js` with CSS `index-DKItHT2C.css`.
- `uv run python -m compileall -q src`: passed after update-info and settings cleanup changes.
- Direct Python update-info smoke check: read local `maa-cli 0.7.5`, `MaaCore 6.13.0`; one transient GitHub timeout for maa-cli version API was observed and surfaced as an error.
- After restarting real 8000 service:
  - `GET /api/settings`: passed; deprecated `game_day_offset_hours` no longer appears in merged timezone settings.
  - `GET /api/maintenance/update-info`: passed; reported MaaCore `v6.13.0`, maa-cli `0.7.5`, hot-resource update unavailable, no errors.
  - `GET /settings`: passed; served `index-C_DhaW-w.js` and `index-DKItHT2C.css`.

## Mistakes

- Initial scratch API verification accidentally touched the real repository root because `create_app(repo_root)` still climbed to `/root/Linux_maa`. It created and deleted a test-only `daily.toml`, leaving a `config/maa/.trash/20260630-013501-daily-925506a0/` entry. That entry was removed immediately. Existing real config files were not modified.
- Tried bare `python` for an API smoke script; this environment has no `python` command on PATH. Use `uv run python` for project Python commands.
- `fastapi.testclient.TestClient` failed again due missing `httpx2`; used real uvicorn plus `curl` instead.

## Active Environment Effects

- `tomli-w` is installed in the active uv environment and recorded in project dependencies.
- `frontend/dist/` was regenerated by `npm run build`; it is ignored by git.
- WebUI backend is running on `0.0.0.0:8000` from this session.
- Previous 8000 WebUI process `17748/17753` was stopped and replaced with current process `52875` to load the new backend/frontend. Active command: `uv run linux-maa webui --host 0.0.0.0 --port 8000`.
- Confirmed from uvicorn logs: browser client `192.168.5.21` issued successful `PUT /api/settings` requests after the restart. This created/updated real `config/linux-maa/settings.toml`, `config/maa/cli.toml`, and related config changes; do not treat those as accidental test artifacts.
- Current WebUI process after latest restart is PID `16699`, serving `0.0.0.0:8000`.

## Durable Notes

- Visual TOML saves currently rebuild the file from structured data and do not preserve original comments/manual formatting.

## Latest Settings Cleanup

- Confirmed: Settings page was tightened after user review. Ordinary-user UI now hides MaaCore component split toggles, maa-cli binary component toggle, SSH update options, profile custom/global/platform resource controls, and other settings that are either auto-handled or too easy to misuse.
- Confirmed: Hidden maa-cli component toggles are normalized to recommended full-install values on settings load/save: `core.components.library = true`, `core.components.resource = true`, and `cli.components.binary = true`.
- Confirmed: Settings descriptions now use a shared question-mark tooltip (`HelpTooltip`) instead of visible explanatory text under every field.
- Confirmed: Profile and maa-cli config file path lines were moved out of the Theme area and into their owning settings cards. Theme controls were folded into the framework card and still apply immediately through localStorage.
- Confirmed: Update-info UI no longer compares base resource `version.json:last_updated` against MaaCore release `published_at`. It now separately shows MaaCore/base package version, maa-cli version, hot-resource git commit, local base resource file metadata, and local hot-resource file metadata.
- Confirmed: Local runtime resource files currently both report `砺火成锋` with raw `last_updated = 2026-06-26 10:29:15.000`; local MaaResource commit and remote main are both `e0130203bc6e97911b8e8f9863a87d7fd0470537`, so hot resources are already latest.
- Confirmed: MAA GUI parses `version.json:last_updated` as UTC and displays local time. The GUI screenshot's 2026-06-28 value was the software/Core build date, not the resource date.

### Latest Tests

- `npm run build` in `frontend/`: passed after settings cleanup/tooltip/update-info fixes. Latest built bundle is `index-DUaLCdpt.js` with CSS `index-pdiSoDG7.css`; Vite reported only the existing large chunk warning.
- `uv run python -m compileall -q src`: passed after the settings cleanup changes.
- `GET /settings` on the active 8000 service: passed; served the new `index-DUaLCdpt.js` bundle and `index-pdiSoDG7.css`.
- `GET /api/settings`: passed; current effective timezone is `Europe/London` / `UTC+01:00` from saved user settings.
- `GET /api/maintenance/update-info`: passed; reported MaaCore `v6.13.0`, maa-cli `0.7.5`, hot-resource local/remote commit equal, no errors.
- Browser screenshot verification became available after installing Playwright. Captured:
  - `.codex/conversations/2026-06-30_0124-config-save-delete/scratch/settings-desktop.png`
  - `.codex/conversations/2026-06-30_0124-config-save-delete/scratch/settings-narrow.png`
- Playwright overflow check on `/settings` passed for `1440x1000` and `520x900`: `documentElement.scrollWidth === clientWidth` and no off-viewport elements were found.
- Visual observation from screenshots: at 1440px the settings page is still a two-column layout with the update/resource card below the first column; at 520px the page stacks vertically without horizontal scrolling.

### Latest Active Effects

- No backend restart was needed for the latest settings-page-only changes. The active WebUI PID `16699` is serving the regenerated `frontend/dist/` assets.
- Installed frontend dev dependency `playwright@^1.61.1`, modifying `frontend/package.json` and `frontend/package-lock.json`.
- Ran `npx playwright install --with-deps chromium`. Debian packages for browser rendering were installed/upgraded, including font packages, `xvfb`, NSS/Pango/Cairo/XKB/AT-SPI related libraries; `libglib2.0-0` and `libglib2.0-data` were upgraded to `2.74.6-2+deb12u9`.
- Playwright browser cache now includes Chromium/Chrome for Testing and headless shell under `/root/.cache/ms-playwright/`.

## JSON Forms Array Renderer

- Confirmed: Added reusable `frontend/src/components/PrimitiveArrayEditor.tsx` for primitive array editing. It provides framed array sections, plus-button add, row checkboxes, hover delete, drag sorting, free-value rename, and enum-value dropdown editing.
- Confirmed: `frontend/src/lib/jsonformsRenderers.tsx` now intercepts `isPrimitiveArrayControl` with the reusable editor. Complex/object arrays still fall through to default JSON Forms renderers.
- Confirmed: Free string arrays such as `Mall.buy_first` and `Mall.blacklist` use rename rows and direct `+` creation.
- Confirmed: Enum arrays such as `Infrast.facility` use no-arrow icon select triggers in place of rename. Dropdowns now show all allowed enum values; selecting a value already present elsewhere swaps the two rows so `uniqueItems` remains valid.
- Confirmed: For full unique enum arrays, the add `+` remains clickable and opens a disabled `已全部添加` item instead of appearing broken.
- Confirmed: Fixed primitive array editor styling after user review:
  - Enum row edit trigger now uses Radix Select `asChild` with the same shadcn icon button styling as free-value rename buttons.
  - The broad `.jsonforms-surface button` fallback CSS now excludes `data-slot="button"`, so local shadcn buttons are not restyled as generic JSON Forms buttons.
  - Array title tooltip buttons now carry `data-tooltip-help`, preventing the pale elongated fallback button frame.
  - Array title add buttons now have hover feedback from `Button` and explicit `active:scale-95` press feedback.
- Tests:
  - `npm run build`: passed after the array renderer changes. Latest bundle from that run was `index-CISY3auj.js` with CSS `index-Bde0cE_O.css`.
  - `uv run python -m compileall -q src`: passed.
  - Playwright `2560x1220` screenshots/checks for Mall and Infrast editor pages passed with no horizontal overflow.
  - Playwright verified `Infrast.facility` row dropdown exposes 9 options and selecting existing `贸易站` from the first row swaps first two rows to `贸易站 / 制造站`.
  - Playwright verified full `Infrast.facility` add trigger is enabled and opens a disabled `已全部添加` option.
  - Playwright style check after the final styling fix confirmed free rename and enum select triggers are both `28x28`, no extra border/padding, and both reach opacity `0.7` on row hover. The title tooltip button is `16x16` with no fallback frame.
