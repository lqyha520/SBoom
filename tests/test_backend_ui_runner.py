"""浏览器回归入口契约；不启动服务、不连接数据库。"""

import subprocess
import unittest
from unittest.mock import Mock, patch

import run_ui_contracts as runner


class BrowserRunnerTests(unittest.TestCase):
    def test_new_suites_use_isolated_fixture_and_matching_browser_script(self):
        for suite, fixture, script in (
            ("discovery", "tests/profile_ui_fixture.py", "tests/mini-discovery-ui.cjs"),
            ("performance", "tests/ui_fixture.py", "tests/mini-performance-ui.mjs"),
        ):
            with self.subTest(suite=suite):
                process = Mock()
                process.poll.return_value = None
                response = Mock()
                response.json.return_value = {"fixture": True}
                with patch.object(runner.subprocess, "Popen", return_value=process) as launch, \
                     patch.object(runner.subprocess, "run") as execute, \
                     patch.object(runner.httpx, "get", return_value=response):
                    runner.run_fixture(suite)
                self.assertIn(suite, runner.SUITES)
                self.assertEqual(launch.call_args.args[0][1], fixture)
                self.assertEqual(execute.call_args.args[0], ["node", script])
                env = execute.call_args.kwargs["env"]
                self.assertEqual(env["MINI_UI_BASE"], env["DISCOVERY_UI_BASE"])
                self.assertTrue(env["MINI_UI_BASE"].startswith("http://127.0.0.1:"))
                self.assertEqual(env["LC_SEED_MINI_FIXTURE"], "1")
                self.assertEqual(env["LC_WEB_DIST"], str(runner.ROOT / "miniprogram" / "dist" / "build" / "h5"))
                self.assertTrue(execute.call_args.kwargs["check"])
                process.terminate.assert_called_once()
                process.wait.assert_called_once_with(timeout=10)

    def test_browser_failure_fails_runner_and_stops_fixture(self):
        process = Mock()
        process.poll.return_value = None
        response = Mock()
        response.json.return_value = {"fixture": True}
        with patch.object(runner.subprocess, "Popen", return_value=process), \
             patch.object(runner.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "browser")), \
             patch.object(runner.httpx, "get", return_value=response):
            with self.assertRaises(subprocess.CalledProcessError):
                runner.run_fixture("performance")
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=10)
