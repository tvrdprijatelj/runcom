import io
import json
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from pages_switcher import App, PagesClient, identify_page, monitor_delay_ms


def state(branch="main"):
    return {"source": {"branch": branch, "path": "/"}, "build_type": "legacy", "status": "built"}


class PagesTests(unittest.TestCase):
    def test_live_page_identification_requires_known_title(self):
        self.assertEqual(identify_page('<title>Runcom — Underhåll / Maintenance</title>'), 'maintenance')
        self.assertEqual(identify_page('<title>Runcom — Välj språk / Choose language</title>'), 'main')
        self.assertIsNone(identify_page('<title>Server error</title>Underhåll'))

    @patch('pages_switcher.urlopen')
    def test_probe_has_no_token_and_build_failure_is_nonfatal(self, urlopen):
        client = PagesClient('private-token')
        response = urlopen.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = b'<title>Unknown</title>'
        with patch.object(client, 'status', return_value=state()), patch.object(client, 'request', side_effect=ValueError('Build unavailable')):
            data = client.detailed_status()
        self.assertEqual(data['build_warning'], 'Build unavailable')
        self.assertIsNone(data['live_mode'])
        self.assertFalse(urlopen.call_args.args[0].has_header('Authorization'))

    def test_status_diagnostics_run_concurrently(self):
        client = PagesClient("test")
        all_started = threading.Barrier(3)

        def status():
            all_started.wait(timeout=2)
            return state()

        def build(**kwargs):
            all_started.wait(timeout=2)
            return {"status": "built"}

        def live():
            all_started.wait(timeout=2)
            return {"live_mode": "main", "live_http": 200}

        with patch.object(client, "status", side_effect=status), patch.object(client, "request", side_effect=build), patch.object(client, "live_status", side_effect=live):
            result = client.detailed_status()
        self.assertEqual(result["latest_build"]["status"], "built")
        self.assertEqual(result["live_mode"], "main")

    def test_actions_return_without_waiting_for_diagnostics(self):
        for action in ("switch", "rebuild"):
            app = Mock()
            app.branch = "main"
            app.pending = False
            app.token.get.return_value = "test"
            app.run.side_effect = lambda operation: operation()
            with patch("pages_switcher.PagesClient") as factory:
                getattr(App, action)(app)
                getattr(factory.return_value, action).assert_called_once_with("main")
                factory.return_value.detailed_status.assert_not_called()

    def test_switch_both_directions(self):
        for current, target in [("main", "maintenance"), ("maintenance", "main")]:
            client = PagesClient("test")
            with patch.object(client, "request", side_effect=[state(current), {}, {"status": "queued"}]) as request:
                self.assertEqual(client.switch(current)["source"]["branch"], target)
                self.assertEqual(request.call_args_list[1].args, ("PUT", {"source": {"branch": target, "path": "/"}}))
                self.assertEqual(request.call_args_list[2].args, ("POST",))
                self.assertEqual(request.call_args_list[2].kwargs, {"suffix": "/builds"})
                self.assertEqual(request.call_count, 3)

    def test_monitoring_is_fast_first_and_backs_off(self):
        self.assertEqual(monitor_delay_ms(0, build_requested=True), 750)
        self.assertEqual(monitor_delay_ms(10), 1500)
        self.assertEqual(monitor_delay_ms(30), 3000)
        self.assertEqual(monitor_delay_ms(120), 5000)

    def test_republish_preserves_branch_and_reports_failure(self):
        client = PagesClient("test")
        with patch.object(client, "request", side_effect=[state("maintenance"), ValueError("Forbidden")]) as request:
            with self.assertRaisesRegex(ValueError, "byggbegäran misslyckades"):
                client.rebuild("maintenance")
            self.assertEqual(request.call_args.args, ("POST",))

    def test_changed_source_does_not_write(self):
        client = PagesClient("test")
        with patch.object(client, "request", return_value=state("maintenance")) as request:
            with self.assertRaises(ValueError):
                client.switch("main")
            self.assertEqual(request.call_count, 1)

    def test_unsupported_configuration_does_not_write(self):
        for data in [dict(state(), build_type="workflow"), state("other"), {"source": None}]:
            client = PagesClient("test")
            with patch.object(client, "request", return_value=data) as request:
                with self.assertRaises(ValueError):
                    client.switch("main")
                self.assertEqual(request.call_count, 1)

    @patch("pages_switcher.urlopen")
    def test_request_and_empty_response(self, urlopen):
        urlopen.return_value.__enter__.return_value.read.return_value = b""
        self.assertEqual(PagesClient("test").request("PUT", {"source": {"branch": "main", "path": "/"}}), {})
        req = urlopen.call_args.args[0]
        self.assertEqual(req.method, "PUT")
        self.assertEqual(json.loads(req.data)["source"]["branch"], "main")

    @patch("pages_switcher.urlopen")
    def test_missing_token_and_auth_error(self, urlopen):
        with self.assertRaises(ValueError):
            PagesClient("").status()
        urlopen.assert_not_called()
        urlopen.side_effect = HTTPError("https://api.github.com", 401, "secret", {}, io.BytesIO(b""))
        with self.assertRaisesRegex(ValueError, "ogiltig"):
            PagesClient("test").status()


if __name__ == "__main__":
    unittest.main()
