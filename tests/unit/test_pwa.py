import asyncio
import io
import json
import os
import re
import unittest

os.environ.setdefault("INGEST_ENABLED", "false")
os.environ.setdefault("ALLOWED_HOSTS", "testserver,localhost")

import httpx  # noqa: E402
from PIL import Image  # noqa: E402

from api.main import app  # noqa: E402


def get(path):
    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path)

    return asyncio.run(send())


class InstallableAppTests(unittest.TestCase):
    def test_manifest_meets_android_install_requirements(self):
        response = get("/manifest.webmanifest")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("application/manifest+json"))
        manifest = response.json()
        self.assertEqual(manifest["display"], "standalone")
        self.assertTrue(manifest["name"] and manifest["short_name"])
        self.assertEqual(manifest["scope"], "/")
        self.assertTrue(manifest["start_url"].startswith("/"))
        sizes = {(icon["sizes"], icon["purpose"]) for icon in manifest["icons"]}
        self.assertIn(("192x192", "any"), sizes)
        self.assertIn(("512x512", "any"), sizes)
        self.assertIn(("512x512", "maskable"), sizes)
        for shortcut in manifest["shortcuts"]:
            self.assertEqual(get(shortcut["url"].split("?")[0]).status_code, 200)

    def test_every_manifest_icon_exists_with_the_declared_size(self):
        for icon in get("/manifest.webmanifest").json()["icons"]:
            response = get(icon["src"])
            self.assertEqual(response.status_code, 200, icon["src"])
            self.assertEqual(response.headers["content-type"], "image/png")
            image = Image.open(io.BytesIO(response.content))
            self.assertEqual(f"{image.width}x{image.height}", icon["sizes"], icon["src"])

    def test_maskable_icon_is_full_bleed(self):
        image = Image.open(io.BytesIO(get("/assets/icons/maskable-512.png").content)).convert("RGBA")
        for corner in ((0, 0), (511, 0), (0, 511), (511, 511)):
            self.assertEqual(image.getpixel(corner)[3], 255)  # opaque to the edge so the OS mask can crop it

    def test_service_worker_is_served_from_root_and_not_cached(self):
        response = get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response.headers["content-type"])
        self.assertEqual(response.headers["service-worker-allowed"], "/")
        self.assertEqual(response.headers["cache-control"], "no-cache")

    def test_every_file_the_service_worker_precaches_exists(self):
        # cache.addAll() rejects if any entry 404s, which would stop the app from installing
        source = get("/sw.js").text
        shell = re.search(r"const SHELL = \[(.*?)\];", source, re.S).group(1)
        paths = re.findall(r'"(/[^"]*)"', shell)
        self.assertGreater(len(paths), 5)
        for path in paths:
            self.assertEqual(get(path).status_code, 200, path)

    def test_service_worker_never_caches_writes_or_other_origins(self):
        source = get("/sw.js").text
        self.assertIn('request.method !== "GET"', source)
        self.assertIn("url.origin !== self.location.origin", source)

    def test_pages_link_the_manifest_and_install_script(self):
        html = get("/").text
        self.assertIn('rel="manifest"', html)
        self.assertIn("/assets/pwa.js", html)
        self.assertIn("apple-touch-icon", html)
        self.assertIn('id="install-app"', html)

    def test_install_script_does_not_require_inline_scripts(self):
        self.assertNotIn("<script>", get("/").text)  # CSP forbids inline scripts


if __name__ == "__main__":
    unittest.main()
