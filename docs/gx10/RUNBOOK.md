# GX10 + Intel Mac runbook (demo day, 1 PM)

Do the steps in order. Times are estimates. A **cutoff** means: if the step
isn't done by then, stop and fall back. The current manual setup works as long
as the GX10 is not rebooted.

| # | Step | Time | Required |
| --- | --- | --- | --- |
| 0 | Copy the files to the GX10 | 3 min | yes |
| 1 | Health check of the current setup | 5 min | yes |
| 2 | Gateway supervision and restart test | 15 min | yes (cutoff 12:15) |
| 3 | Brain server on the GX10 | 20 min | **optional**; skip unless step 2 finished early |
| 4 | Mac-side flags | 5 min | yes |
| 5 | Demo rehearsal | 20 min | yes |
| 6 | Failure drills | 10 min | recommended |
| 7 | Rollback, if anything goes wrong | 2 min | as needed |

Ground rules:

- **Never print a token.** Don't use `cat tokens.json`, `echo $TOKEN` or
  `curl -H "Authorization: Bearer <literal>"`. The scripts read tokens from
  files or Keychain into headers.
- Don't rotate tokens. Don't change the Serve `:443` mount. Never run a
  second gateway. Never use `tailscale funnel`.
- **Don't reboot the GX10 without checking with whoever else uses it.**

Placeholders used below: GX10 is `asus@100.111.110.43`; the inference origin
is `https://6wjp.tail4cc204.ts.net`.

---

## 0. Copy the files to the GX10 (3 min)

Run this on the Mac, from the Wisp checkout that contains `deploy/gx10`:

```sh
rsync -a --relative --exclude __pycache__ \
  brain_server service/__init__.py service/behavior deploy/gx10 \
  asus@100.111.110.43:wisp-src/
ssh asus@100.111.110.43 'ls ~/wisp-src/deploy/gx10'
```

## 1. Health check of the current setup (5 min)

**On the Mac.** This is read-only and uses the Keychain token without printing
it:

```sh
bash deploy/gx10/mac-check-gateway.sh
```

Expected output:

- reachable, with unauthenticated `401`;
- the token found in Keychain;
- `/v1/models -> 200 and lists qwen3.6:35b`;
- `chat completion -> 200 in N s`.

The first chat after an idle period can take longer while Ollama loads the
35B model.

**On the GX10:**

```sh
ssh asus@100.111.110.43
bash ~/wisp-src/deploy/gx10/healthcheck.sh
```

Expected output:

- Ollama answering;
- a listener on `:8767` (today that's the manual process);
- unauthenticated `/v1/models -> 401`;
- `tailscale serve status` shows `:443` proxying to `http://127.0.0.1:8767`.

If anything is red, fix it before you continue. The table in
`GATEWAY_SUPERVISION.md` covers the common cases.

## 2. Gateway supervision (15 min, cutoff 12:15)

Run on the GX10 as `asus`.

```sh
cd ~/wisp-src/deploy/gx10
bash install-gateway-service.sh --dry-run          # read the rendered unit + planned actions
bash install-gateway-service.sh                    # installs + ENABLES; won't start a duplicate
```

The installer prints "Using the running gateway's interpreter: …". It may also
warn about env vars the manual process has. If it lists any, decide whether
`gateway.py` needs them before taking over.

Switch the running gateway to systemd. The Mac sees a gap of a few seconds,
so don't do this while someone is demoing:

```sh
bash install-gateway-service.sh --takeover
```

If the unit doesn't become healthy, the installer rolls back by itself and
relaunches the old manual command. Then it exits with an error; read
`journalctl --user -u wisp-gx10-gateway -n 80`.

Enable start at boot without a login:

```sh
loginctl show-user asus -p Linger            # want Linger=yes
loginctl enable-linger asus || sudo loginctl enable-linger asus
```

Verify that the gateway survives a restart and a crash:

```sh
systemctl --user restart wisp-gx10-gateway && sleep 3 && systemctl --user is-active wisp-gx10-gateway
systemctl --user kill -s SIGKILL wisp-gx10-gateway; sleep 8; systemctl --user status wisp-gx10-gateway --no-pager | head -5
bash ~/wisp-src/deploy/gx10/healthcheck.sh   # expect "gateway is supervised by systemd"
```

Then run `bash deploy/gx10/mac-check-gateway.sh` again **on the Mac**. It
should be all green.

**Reboot test.** Do this only if a reboot of the shared GX10 is agreed:

```sh
sudo systemctl reboot
# from the Mac, ~2-4 min later (do NOT ssh in first: we're proving it starts without a login):
bash deploy/gx10/mac-check-gateway.sh
# then on the GX10:
systemctl --user status wisp-gx10-gateway; journalctl --user -u wisp-gx10-gateway -b --no-pager | tail -20
```

If no reboot is agreed, linger plus an enabled unit is the documented
mechanism, but unattended boot start remains **unverified**. Say so if asked.

**If you hit the cutoff:** leave things as they are. If the manual gateway is
still running, Send works. Having the unit installed and enabled can't hurt:
it only starts at the next boot, and it refuses to start if the port is taken.

## 3. Optional: brain server on the GX10 (20 min)

**Skip this for the 1 PM demo unless step 2 is done and verified.** The demo's
default, and its privacy story, is that the behavior engine runs in-process on
the Mac (`brain.mode local`). Remote mode is a stretch goal.

On the GX10:

```sh
cd ~/wisp-src/deploy/gx10
bash install-brain.sh --dry-run
bash install-brain.sh --serve        # venv + token + unit on 127.0.0.1:8790 + tailscale serve https :8443
```

`--serve` first reads `tailscale serve status --json` and REFUSES (before
installing anything) if `:8443` already serves something other than
`http://127.0.0.1:8790`; if it already points there it is left as is. It also
refuses when the status cannot be read (operator permission). Then it prints
`:443 Serve mount unchanged`. If it prints a WARNING instead,
roll back with `uninstall-brain.sh --serve-off` and compare the two JSON
snapshots it saved in `~/.local/state/wisp-brain/`.

If `tailscale serve` is refused for permissions, run
`sudo tailscale serve --bg --https=8443 http://127.0.0.1:8790`. Then check:

```sh
tailscale serve status     # expect :443 -> 127.0.0.1:8767 (unchanged) AND :8443 -> 127.0.0.1:8790
curl -s http://127.0.0.1:8790/healthz      # {"ok":true,"engine":"ready"}
```

If `/healthz` returns `503 {"engine":"unavailable"}`, the copied code predates
the finished engine. Re-run step 0 with the current checkout, then run
`install-brain.sh` again.

The phraser uses the same Ollama model as the gateway, so no second model is
loaded. For template-only text, use `--no-phraser`.

### Brain token to the Mac

This never displays the token. The runtime reads Keychain service
`com.wisp.inference`, account `wispbrain:<sha256(WISP_BRAIN_URL)>`, where the
URL is exactly as configured, with no trailing slash. Run on the Mac:

```sh
BRAIN_URL=https://6wjp.tail4cc204.ts.net:8443
ssh asus@100.111.110.43 'cat ~/.config/wisp-brain/token' | tr -d '\n' | pbcopy
security add-generic-password -U -s com.wisp.inference \
  -a "wispbrain:$(printf %s "$BRAIN_URL" | shasum -a 256 | awk '{print $1}')" -w
# at the "password data" prompt(s): Cmd-V, Return
pbcopy < /dev/null      # clear the clipboard
bash deploy/gx10/mac-check-gateway.sh --no-chat --brain "$BRAIN_URL"
```

`WISP_BRAIN_TOKEN` in the environment also works. It is visible to anything
that can read the process environment, so use it for a quick test only.

## 4. Mac-side flags (5 min)

> **Integrator to finalize.** The values below are what
> `service/assistant/behavior_runtime.py` reads today. Confirm them against
> `docs/BEHAVIOR_DEMO.md` before the demo.

| Flag | Value | Notes |
| --- | --- | --- |
| `WISP_REMOTE_ONLY` | `1` | Existing Intel build. All model roles go to the GX10. |
| `WISP_FOUNDER_DEMO` | `1` | Existing. Implies behavior on, with synthetic data only. |
| `WISP_BEHAVIOR` | `1` | Behavior engine on. Implied by the founder demo. |
| `WISP_BEHAVIOR_SYNTHETIC_ONLY` | `1` | Learn from the fictional persona and the `Wisp Demo` calendar only. |
| `WISP_BRAIN_MODE` | `local` (default) or `remote` | Or set `brain: {mode, url}` in the models config. |
| `WISP_BRAIN_URL` | `https://6wjp.tail4cc204.ts.net:8443` | Remote only. No trailing slash: the Keychain account hashes it. |
| `WISP_BEHAVIOR_PHRASER` | `0` to disable | Local engine only. Template text, no GX10 phrasing calls. |

In `local` mode the GX10 sees only chat inference and the short phrasing
requests. In `remote` mode the Mac sends observations (titles, contacts and
times; never message text) to the brain on the GX10, over Tailscale only.

## 5. Demo rehearsal (20 min)

Follow `docs/BEHAVIOR_DEMO.md` for the exact seeding and presets. Then run
these beats:

1. **Green board.** Run `mac-check-gateway.sh`; all checks should be `[ok]`.
   Open Wisp and confirm Send answers.
2. **It noticed.** A nudge card appears, for example a gym clash or a
   meeting that's likely to be cancelled. Point at the "because" line. That's
   the evidence, composed by code.
3. **Ask about yourself.** Ask "What do you know about my week?" The answer
   comes from `describe_me` and `predict_my_day`.
4. **Correct it.** Reject or confirm a pattern (`correct_pattern`), or give
   the nudge feedback "wrong". That kind of nudge is muted.
5. **Optional, only after drill 6a is rehearsed:** stop the gateway and show
   that nudges still appear. Learning is local and phrasing falls back to
   templates. Then restart the gateway.

## 6. Failure drills (10 min)

**a) Gateway down, then recovery.** On the GX10:

```sh
systemctl --user stop wisp-gx10-gateway
```

On the Mac, `mac-check-gateway.sh` now reports HTTP `502`. Send fails, and
nudges and cards still show with template text. Recover on the GX10:

```sh
systemctl --user start wisp-gx10-gateway
```

Re-run the Mac check; it should be green within about 5 s. Also run the crash
variant: `systemctl --user kill -s SIGKILL wisp-gx10-gateway`. It restarts by
itself after 5 s.

**b) GX10 unreachable.** Turn off Tailscale on the Mac.

- Chat fails. That's expected in the remote-only build.
- In `local` mode the behavior engine keeps running in-process: ingest, mine,
  predict and nudge all work with template text, because phrasing returns
  `None`.
- In `remote` mode the runtime falls back to the local engine for 120 s at a
  time. The profile card is served from the cached
  `behavior_profile_card.txt`.

Turn Tailscale back on and re-check.

**c) Remote brain down** (only if step 3 was done). On the GX10:

```sh
systemctl --user stop wisp-brain
```

The Mac keeps working on its local engine. Restore with
`systemctl --user start wisp-brain`.

## 7. Rollback (2 min)

Gateway supervision. This relaunches the manual command; it won't survive a
reboot:

```sh
bash ~/wisp-src/deploy/gx10/rollback-gateway-service.sh --dry-run
bash ~/wisp-src/deploy/gx10/rollback-gateway-service.sh
```

Brain server. Data and token are kept unless you pass `--purge`:

```sh
bash ~/wisp-src/deploy/gx10/uninstall-brain.sh --serve-off       # removes :8443 only if it points to 127.0.0.1:8790 (--port N otherwise)
bash ~/wisp-src/deploy/gx10/uninstall-brain.sh --restore-previous # or: go back to the previous code
```

Mac: remove `WISP_BRAIN_MODE` and `WISP_BRAIN_URL`. Behavior then runs locally.
To turn behavior off completely, remove `WISP_BEHAVIOR*`. The cleanup section
of `docs/BEHAVIOR_DEMO.md` has the rest.

---

### Verification status (be honest if asked)

- **Verified in a Linux sandbox:**
  - script syntax and shellcheck;
  - unit files pass `systemd-analyze verify`;
  - installer detection, refusal, takeover and auto-rollback, using stubbed
    systemd and a fake gateway;
  - the brain server installed into a venv and served `healthz`, auth (`401`)
    and the 2 MB limit (`413`) over real HTTP;
  - client/server round-trip tests;
  - phraser contract tests, including passing `RemoteOnlyProfile.validate_payload`.
- **Not verified, because the GX10 and the Mac were unreachable:**
  - the real systemd user manager, linger and boot start on DGX OS;
  - Tailscale Serve `:8443`;
  - Ollama phrasing quality and latency with `qwen3.6:35b` (including
    whether it honours `/no_think`);
  - Keychain commands on the Intel Mac.
