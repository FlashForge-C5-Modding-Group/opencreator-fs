"""moonraker-repo.sh puts a Moonraker checkout Moonraker's update manager calls
invalid back on origin/master, and hides the links OpenCreator makes in it.

Runs on a small local repo standing in for Moonraker; no network."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "fs/usr/data/opencreator/startup/moonraker-repo.sh"
URL = "https://github.com/Arksine/moonraker.git"


class MoonrakerRepo(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.mr = self.root / "moonraker"
        (self.mr / "moonraker/components").mkdir(parents=True)
        (self.mr / "moonraker/components/__init__.py").write_text("")
        self.env = dict(os.environ, HOME=str(self.root), OC_MOONRAKER=str(self.mr),
                        GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        self.git("init", "-q", "-b", "master")
        self.git("add", ".")
        self.git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "first")
        self.head = self.git("rev-parse", "HEAD")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.mr), *args], env=self.env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def git_or_none(self, *args):
        r = subprocess.run(["git", "-C", str(self.mr), *args], env=self.env, capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None

    def run_script(self, action):
        return subprocess.run(["sh", str(SCRIPT), action], env=self.env, check=True,
                              capture_output=True, text=True).stdout

    def test_detached_without_a_remote(self):
        # the state that shows "Failed to detect git branch / repo url"
        self.git("checkout", "-q", "--detach")
        self.git("branch", "-q", "-D", "master")
        self.run_script("repair")
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), "master")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.head)  # same commit, no files changed
        self.assertEqual(self.git("remote", "get-url", "origin"), URL)
        self.assertEqual(self.git("config", "branch.master.remote"), "origin")
        self.assertEqual(self.git("config", "branch.master.merge"), "refs/heads/master")

    def test_other_remote_and_a_tag_only_fetch(self):
        self.git("remote", "add", "origin", "https://github.com/someone/moonraker.git")
        self.git("config", "remote.origin.fetch", "+refs/tags/v0.9.3:refs/tags/v0.9.3")
        self.run_script("repair")
        self.assertEqual(self.git("remote", "get-url", "origin"), URL)
        self.assertEqual(self.git("config", "--get-all", "remote.origin.fetch"),
                         "+refs/heads/master:refs/remotes/origin/master")

    def test_healthy_checkout_is_left_alone(self):
        self.git("remote", "add", "origin", URL)
        self.git("config", "branch.master.remote", "origin")
        self.git("config", "branch.master.merge", "refs/heads/master")
        self.assertEqual(self.run_script("repair"), "")

    def test_other_branch_is_kept(self):
        self.git("checkout", "-q", "-b", "mine")
        self.run_script("repair")
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), "mine")
        self.assertIsNone(self.git_or_none("config", "branch.mine.remote"))

    def test_live_never_replaces_a_broken_checkout(self):
        shutil.rmtree(self.mr / ".git")
        out = self.run_script("live")
        self.assertIn("next boot", out)
        self.assertTrue((self.mr / "moonraker/components/__init__.py").is_file())

    def test_links_are_hidden_but_real_files_are_not(self):
        target = self.root / "component.py"
        target.write_text("")
        comps = self.mr / "moonraker/components"
        (comps / "opencreator_3mf.py").symlink_to(target)
        (comps / "timelapse.py").symlink_to(target)
        (comps / "mine.py").write_text("")
        self.run_script("exclude")
        self.assertEqual(self.git("status", "--porcelain"), "?? moonraker/components/mine.py")
        # a link that goes away is dropped from the list, the rest of the file kept
        exclude = self.mr / ".git/info/exclude"
        exclude.write_text(exclude.read_text() + "*.mine\n")
        (comps / "timelapse.py").unlink()
        self.run_script("exclude")
        text = exclude.read_text()
        self.assertNotIn("timelapse.py", text)
        self.assertIn("/moonraker/components/opencreator_3mf.py", text)
        self.assertIn("*.mine", text)
        self.assertEqual(text.count("# opencreator links begin"), 1)


if __name__ == "__main__":
    unittest.main()
