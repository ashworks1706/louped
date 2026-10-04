"""Put the UI's static export in the wheel as louped/web, so `pip install louped` serves it.

The export is built by `just web-build` (CI and the release build it first). An editable install
reads apps/web/out from the checkout instead, so it needs nothing here.
"""

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class WebHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        if self.target_name != "wheel" or version == "editable":
            return
        out = Path(self.root, "apps", "web", "out")
        if not (out / "index.html").is_file():
            print("louped: apps/web/out is not built, so this wheel has no UI (run just web-build)")
            return
        build_data["force_include"][str(out)] = "louped/web"
        print(f"louped: the wheel carries the UI from {out}")
