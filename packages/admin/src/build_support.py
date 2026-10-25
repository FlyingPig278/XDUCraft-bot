"""Prevent publishing a wheel with an accidentally missing management UI."""
from pathlib import Path

from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self):
        static = Path(__file__).parent / "xducraft_admin" / "static" / "index.html"
        if not self.editable_mode and not static.is_file():
            raise RuntimeError(
                "WebUI assets are missing. Run npm ci && npm run build in webui/ "
                "before building the admin distribution."
            )
        super().run()
