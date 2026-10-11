"""Aria demo (WISP_ARIA_DEMO=1 on the full remote build): synthetic world,
dispatch boundary, approvals, reset and state separation.

Synthetic only: fresh WISP_HOME, sockets forbidden, every native tool
implementation replaced by a mock that fails the test if it is called.
"""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import AsyncMock, Mock, patch

if not os.environ.get('WISP_HOME') or Path(os.environ['WISP_HOME']).resolve() == Path.home() / '.moe':
    raise RuntimeError('Use a fresh disposable WISP_HOME for Aria demo tests')

import service.main  # noqa: F401,E402 — registers every built-in tool
from fastapi.testclient import TestClient  # noqa: E402

from service.demo.aria import data as aria_data  # noqa: E402
from service.demo.aria import tools as aria_tools  # noqa: E402
from service.demo.aria.world import World, set_world  # noqa: E402
from service.safety import grants, policy as safety  # noqa: E402
from service.tools.registry import REGISTRY, run_tool  # noqa: E402
from tests.test_intel_remote_full import FullFixture, _paths_in_subprocess  # noqa: E402
from tests.test_intel_remote_only_main import selected  # noqa: E402
from tests.test_intel_remote_policy import policy  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ARIA_ENV = {'WISP_REMOTE_ONLY': '1', 'WISP_REMOTE_FULL': '1', 'WISP_ARIA_DEMO': '1'}

# Minimal valid arguments for every synthetic tool.
ARGS = {
    'view_emails': {}, 'summarize_emails': {}, 'summarize_thread': {'subject': 'Foundry'}, 'triage_inbox': {},
    'archive_email': {'message_id': 'mail-001'}, 'flag_email': {'message_id': 'mail-001'},
    'mark_email_read': {'message_id': 'mail-001'},
    'send_email': {'to': 'lena.ortiz@example.com', 'subject': 'Export plan', 'body': 'Retention 13 months.'},
    'draft_email': {'to': 'Lena Ortiz', 'subject': 'Draft', 'body': 'b'},
    'reply_to_email': {'message_id': 'mail-001', 'body': 'Thanks!'},
    'forward_email': {'message_id': 'mail-001', 'to': 'dev.malik@example.com'},
    'view_messages': {}, 'summarize_messages': {}, 'send_message': {'to': 'Mom', 'text': "I'll call at 6"},
    'draft_message': {'to': 'Dev Malik', 'text': 'hi'},
    'schedule_send': {'channel': 'message', 'to': 'Dev Malik', 'when': 'in 2 hours', 'text': 'ping'},
    'list_scheduled_sends': {}, 'cancel_scheduled_send': {'id': 'sched:none'},
    'lookup_contact': {'name': 'Nora Keene'}, 'list_contacts': {},
    'manage_contacts': {'action': 'create', 'name': 'Rae Demo', 'value': 'rae@example.com'},
    'search_notes': {'query': 'runway'}, 'create_note': {'title': 'Demo note', 'body': 'x'},
    'append_note': {'title': 'Demo note', 'text': 'more'},
    'search_reminders': {'query': 'Priya'}, 'add_reminder': {'title': 'Send board deck', 'when_iso': '2030-01-04T09:00'},
    'update_reminder': {'title': 'Send board deck', 'when_iso': '2030-01-05T09:00'},
    'complete_reminder': {'title': 'Send board deck'}, 'clear_reminders': {'scope': 'tomorrow', 'query': 'zzz'},
    'clear_past_reminders': {'query': 'zzz'},
    'get_upcoming': {}, 'get_past_events': {}, 'find_free_time': {},
    'add_calendar_event': {'title': 'Coffee with Maya', 'when_iso': '2030-01-04T10:00'},
    'cancel_event': {'title': 'Coffee with Maya'},
}


class AriaFixture(FullFixture):
    def setUp(self):
        super().setUp()
        for p in (patch.object(policy, '_ARIA_MODE', '1'), patch.dict(os.environ, ARIA_ENV)):
            p.start()
            self.addCleanup(p.stop)
        policy.remote_only_profile.cache_clear()
        self.clock = [1_800_000_000.0]
        self.world = World(Path(os.environ['WISP_HOME']) / f'world-{id(self)}.db', clock_fn=lambda: self.clock[0])
        set_world(self.world)
        self.addCleanup(lambda: (set_world(None), self.world.close()))
        self.assertTrue(policy.aria_demo_mode())

    def native_bombs(self):
        """Replace every non-passthrough tool's native implementation, the app
        outbox and process spawning with mocks that fail the test if called."""
        bombs = {}
        for name, tool in REGISTRY.items():
            if name in aria_tools.PASSTHROUGH:
                continue
            bomb = Mock(side_effect=AssertionError(f'native {name} reached'))
            bombs[name] = bomb
            p = patch.object(tool, 'func', bomb)
            p.start()
            self.addCleanup(p.stop)
        for target in ('service.assistant.outbox._request', 'subprocess.run', 'subprocess.Popen',
                       'asyncio.create_subprocess_exec'):
            p = patch(target, side_effect=AssertionError(f'{target} reached'))
            p.start()
            self.addCleanup(p.stop)
        return bombs


class DataChecks(AriaFixture):
    def test_dataset_counts_and_fiction_rules(self):
        bundle = aria_data.load()
        self.assertEqual(aria_data.validate(bundle), [])
        self.assertEqual(len(bundle['mail_threads']), 48)
        self.assertEqual(sum(len(t['messages']) for t in bundle['mail_threads']), 99)
        self.assertEqual(len(bundle['chats']), 6)
        self.assertEqual(sum(len(c['messages']) for c in bundle['chats']), 275)
        self.assertEqual(len(bundle['contacts_extra']), 5)
        self.assertEqual(len(bundle['founder']['notes']), 12)
        self.assertEqual(len(bundle['founder']['reminders']), 22)
        out = subprocess.run([sys.executable, str(ROOT / 'service/demo/aria/validate.py')], capture_output=True,
                             text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn('PASS', out.stdout)

    def test_seeded_counts(self):
        counts = self.world.counts()
        for key, value in {'mail_threads': 48, 'mail_messages': 99, 'message_threads': 6, 'messages': 275,
                           'notes': 12, 'reminders': 22, 'contacts': 19}.items():
            self.assertEqual(counts[key], value, key)
        self.assertGreater(counts['events'], 100)

    def test_week_shift_keeps_weekday_and_never_future(self):
        as_of = aria_data.load()['as_of']
        for days in (0, 1, 3, 6, 7, 13, 40):
            now = as_of + days * 86400 + 60
            shift = aria_data.week_shift(as_of, now)
            self.assertEqual(shift % (7 * 86400), 0)
            self.assertLessEqual(as_of + shift, now)
            self.assertGreater(as_of + shift, now - 7 * 86400)


class BoundaryChecks(AriaFixture):
    def test_demo_allowlist_and_policy(self):
        for name in ('send_email', 'send_message', 'add_reminder', 'add_calendar_event', 'create_note',
                     'view_emails', 'get_weather', 'describe_me'):
            self.assertTrue(policy.remote_tool_allowed(name), name)
        for name in ('run_shell', 'read_file', 'trash_file', 'open_app', 'set_volume', 'http_request',
                     'create_tool', 'daily_brief', 'search_browser_history'):
            self.assertFalse(policy.remote_tool_allowed(name), name)
            self.assertIs(safety.decide(REGISTRY[name].category, {}, tool=name).tier, safety.Tier.DENY)
        self.assertEqual(set(aria_tools.SYNTHETIC) - set(REGISTRY), set())

    def test_sends_confirm_every_time_and_writes_ask_normally(self):
        for name in ('send_email', 'send_message', 'reply_to_email', 'forward_email', 'schedule_send'):
            args = ARGS[name]
            self.assertIs(safety.decide(REGISTRY[name].category, args, tool=name).tier, safety.Tier.CONFIRM, name)
            self.assertFalse(grants.is_grantable(name, args), name)
            self.assertIs(grants.grant(name, args, decision='allow').get('ok'), False)
        # A write behaves exactly as in real mode (same decision for the same args).
        args = ARGS['add_reminder']
        demo = safety.decide(REGISTRY['add_reminder'].category, args, tool='add_reminder').tier
        with patch.object(policy, '_ARIA_MODE', None):
            real = safety.decide(REGISTRY['add_reminder'].category, args, tool='add_reminder').tier
        self.assertIs(demo, real)

    def test_dispatch_never_reaches_native_implementations(self):
        bombs = self.native_bombs()
        for name, args in ARGS.items():
            with self.subTest(tool=name):
                result = asyncio.run(run_tool(REGISTRY[name], dict(args)))
                self.assertNotIn('native', result)
                self.assertFalse(result.startswith('(error'), result)
                self.assertIn('Aria demo', result)
        for name in ('run_shell', 'read_file', 'open_app', 'daily_brief', 'trash_file'):
            result = asyncio.run(run_tool(REGISTRY[name], {}))
            self.assertIn('nothing was executed', result)
        for name, bomb in bombs.items():
            bomb.assert_not_called()

    def test_outbox_refuses_without_publishing(self):
        from service.assistant import outbox
        with patch.object(outbox.hub, 'publish', AsyncMock(side_effect=AssertionError('published'))):
            result = asyncio.run(outbox.request('send_message', {'to': '+12025550101', 'text': 'x'}))
        self.assertIs(result['ok'], False)
        self.assertEqual(result['status'], 'not_attempted')

    def test_native_sync_pushes_are_ignored(self):
        names = {'assistant_sync_calendar', 'assistant_sync_emails', 'assistant_sync_notes',
                 'assistant_sync_browser_history', 'assistant_sync_messages'}
        bomb = Mock(side_effect=AssertionError('native data accepted'))
        ns = {'assistant_store': Mock(sync_source=bomb, today_source_unavailable=bomb),
              'assistant_scheduler': Mock(record_sync=bomb), 'HTTPException': Exception}
        selected(names, ns)
        for name in names:
            with self.subTest(endpoint=name):
                self.assertTrue(asyncio.run(ns[name]({'events': [{'title': 'x', 'when_ts': 1}], 'raw': 'x',
                                                      'headers': 'x'}))['ignored_native_sync'])
        bomb.assert_not_called()

    def test_identity_is_aria(self):
        from service.memory import identity
        self.assertEqual(identity.user_name(), 'Aria Solano')
        self.assertEqual(identity.user_emails(), ['aria.solano@example.com'])

    def test_behavior_is_synthetic_local_and_separate(self):
        from service.assistant import behavior_runtime as br
        from service.behavior import flags
        self.assertTrue(flags.env_enabled())
        self.assertTrue(br.synthetic_only())
        with patch.dict(os.environ, {'WISP_BRAIN_MODE': 'remote', 'WISP_BRAIN_URL': 'https://brain.example'}):
            self.assertEqual(br.brain_mode(), 'local')
        with patch.dict(os.environ, {'WISP_BEHAVIOR': '0'}):
            self.assertFalse(flags.env_enabled())


class WorldBehavior(AriaFixture):
    def test_simulated_send_appears_in_thread_with_scripted_reply(self):
        before = self.world.counts()['messages']
        out = asyncio.run(run_tool(REGISTRY['send_message'], {'to': 'Mom', 'text': "I'll call at 6"}))
        self.assertIn('Sent (simulated', out)
        rows = self.world.messages(conversation='Mom', count=3)
        self.assertEqual(rows[0]['text'], "I'll call at 6")
        self.assertEqual(rows[0]['direction'], 'out')
        self.assertEqual(rows[0]['thread_id'], 'chat-mom')  # joins the existing chat
        self.assertEqual(self.world.counts()['messages'], before + 1)  # reply not visible yet
        self.clock[0] += 120
        rows = self.world.messages(conversation='Mom', count=1)
        self.assertEqual(rows[0]['direction'], 'in')
        self.assertEqual(rows[0]['sender'], 'Marisol Solano')
        self.assertEqual(self.world.counts()['messages'], before + 2)

    def test_simulated_email_is_sent_and_answered(self):
        asyncio.run(run_tool(REGISTRY['send_email'], dict(ARGS['send_email'])))
        sent = self.world.mail(folder='sent', count=1)[0]
        self.assertEqual(sent['subject'], 'Export plan')
        self.assertIn('lena.ortiz@example.com', sent['to_addrs'])
        self.clock[0] += 120
        reply = self.world.mail(folder='inbox', count=1)[0]
        self.assertEqual(reply['thread_id'], sent['thread_id'])
        self.assertEqual(reply['from_addr'], 'lena.ortiz@example.com')

    def test_unknown_real_looking_recipient_is_refused(self):
        out = asyncio.run(run_tool(REGISTRY['send_email'], {'to': 'someone@gmail.com', 'subject': 's', 'body': 'b'}))
        self.assertIn('nothing was sent', out)
        self.assertEqual(self.world.mail(folder='sent', query='someone', count=5), [])

    def test_writes_land_in_the_world_and_reset_restores(self):
        seeded = self.world.counts()
        for name in ('add_reminder', 'add_calendar_event', 'create_note', 'send_message', 'schedule_send',
                     'manage_contacts'):
            asyncio.run(run_tool(REGISTRY[name], dict(ARGS[name])))
        self.clock[0] += 120
        changed = self.world.counts()
        for key in ('reminders', 'events', 'notes', 'messages', 'scheduled', 'contacts'):
            self.assertNotEqual(changed[key], seeded[key], key)
        self.assertEqual(self.world.reset(), self.world.counts())
        after = self.world.counts()
        for key in ('reminders', 'notes', 'messages', 'scheduled', 'contacts', 'mail_messages'):
            self.assertEqual(after[key], seeded[key], key)

    def test_scheduled_send_delivers_into_thread(self):
        out = asyncio.run(run_tool(REGISTRY['schedule_send'], dict(ARGS['schedule_send'])))
        self.assertIn('Scheduled (simulated', out)
        self.clock[0] += 3 * 3600
        delivered = self.world.deliver_due()
        self.assertEqual(len(delivered), 1)
        self.assertEqual(self.world.messages(conversation='Dev', count=5)[-1]['direction'] in ('in', 'out'), True)
        self.assertTrue(any(r['text'] == 'ping' for r in self.world.messages(conversation='Dev', count=5)))

    def test_reset_and_status_endpoints(self):
        client = TestClient(service.main.app)
        asyncio.run(run_tool(REGISTRY['create_note'], dict(ARGS['create_note'])))
        status = client.get('/demo/aria/status').json()
        self.assertTrue(status['enabled'])
        self.assertEqual(status['counts']['notes'], 13)
        with patch('service.assistant.behavior_runtime.clear_demo_state') as clear:
            res = client.post('/demo/aria/reset', json={})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()['counts']['notes'], 12)
        clear.assert_called_once()
        with patch.object(policy, '_ARIA_MODE', None):
            self.assertEqual(client.post('/demo/aria/reset', json={}).status_code, 409)
            self.assertEqual(client.get('/demo/aria/status').json(), {'enabled': False, 'counts': None})


class RealModeUnchanged(FullFixture):
    def test_real_mode_dispatches_to_native_implementation(self):
        self.assertFalse(policy.aria_demo_mode())
        native = AsyncMock(return_value='Email sent to friend@example.com.')
        with patch.object(REGISTRY['send_email'], 'func', native):
            out = asyncio.run(run_tool(REGISTRY['send_email'], {'to': 'friend@example.com', 'subject': 's',
                                                                'body': 'b'}))
        native.assert_awaited_once()
        self.assertEqual(out, 'Email sent to friend@example.com.')
        self.assertTrue(policy.remote_tool_allowed('run_shell'))


class StateSeparation(FullFixture):
    def test_aria_state_never_shares_files_with_real_mode(self):
        real = _paths_in_subprocess({'WISP_REMOTE_ONLY': '1', 'WISP_REMOTE_FULL': '1'})
        demo = _paths_in_subprocess(ARIA_ENV)
        home = Path(os.environ['WISP_HOME']).resolve()
        self.assertEqual(Path(demo['state']).resolve(), home / 'aria-demo')
        self.assertEqual(Path(real['state']).resolve(), home)
        for key in ('assistant', 'queue', 'sessions', 'facts', 'grants', 'brief', 'behavior', 'cache'):
            with self.subTest(key=key):
                self.assertTrue(Path(demo[key]).resolve().is_relative_to(home / 'aria-demo'))
                self.assertFalse(Path(real[key]).resolve().is_relative_to(home / 'aria-demo'))
        self.assertEqual(json.loads(json.dumps(real['moe'])), demo['moe'])
