import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class LaunchScriptTests(unittest.TestCase):
    def test_shell_syntax(self):
        for name in ("common.sh", "start_rover.sh", "rover_start_remote.sh",
                     "stop_rover.sh", "start_gcs.sh", "start_video.sh", "start_diagnostics.sh"):
            result = subprocess.run(
                ["bash", "-n", str(ROOT / "scripts" / name)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_scripts_are_executable(self):
        for name in ("start_rover.sh", "rover_start_remote.sh", "stop_rover.sh",
                     "start_gcs.sh", "start_video.sh", "start_diagnostics.sh"):
            self.assertTrue(os.access(ROOT / "scripts" / name, os.X_OK))

    def test_launchers_exist(self):
        desktop = Path.home() / "LOONAR" / "REMOTE"
        for name in ("LOONAR 로버 시작", "LOONAR 로버 종료", "LOONAR 실시간 지상국", "LOONAR 영상 수신"):
            launcher = desktop / name
            self.assertTrue(launcher.exists())
            self.assertTrue(os.access(launcher, os.X_OK))


if __name__ == "__main__":
    unittest.main()
