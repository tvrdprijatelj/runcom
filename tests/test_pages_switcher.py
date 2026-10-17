import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from pages_switcher import PagesClient


def state(branch="main"):
    return {"source": {"branch": branch, "path": "/"}, "build_type": "legacy", "status": "built"}


class PagesTests(unittest.TestCase):
    def test_switch_both_directions(self):
        for current, target in [("main", "maintenance"), ("maintenance", "main")]:
            client = PagesClient("test")
            with patch.object(client, "request", side_effect=[state(current), {}, state(target)]) as request:
                self.assertEqual(client.switch(current)["source"]["branch"], target)
                self.assertEqual(request.call_args_list[1].args, ("PUT", {"source": {"branch": target, "path": "/"}}))

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
        urlopen.side_effect = HTTPError("https://api.github.com", 401, "secret", {}, None)
        with self.assertRaisesRegex(ValueError, "ogiltig"):
            PagesClient("test").status()


if __name__ == "__main__":
    unittest.main()
