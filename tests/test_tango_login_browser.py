import unittest
from pathlib import Path
from threading import Event

from playwright.sync_api import sync_playwright

from lockedin.tango.browser import FEED_URL, TANGO_URL, TangoBrowserSession


class TangoLoginBrowserTests(unittest.TestCase):
    def test_sign_in_redirect_then_open_tango(self) -> None:
        with sync_playwright() as playwright:
            executable = Path(playwright.chromium.executable_path)
            if not executable.exists():
                self.skipTest("Playwright Chromium is not installed")
            browser = playwright.chromium.launch(headless=True, executable_path=str(executable))
            try:
                context = browser.new_context()
                page = context.new_page()
                requests = []

                def route_request(route) -> None:
                    url = route.request.url
                    requests.append(url)
                    if url == FEED_URL and requests.count(FEED_URL) == 1:
                        route.fulfill(
                            content_type="text/html",
                            body="<script>location.href='https://www.linkedin.com/login'</script>",
                        )
                    elif url == "https://www.linkedin.com/login":
                        route.fulfill(
                            content_type="text/html",
                            body=(
                                "<script>setTimeout(() => {"
                                "document.cookie='li_at=test; path=/; secure';"
                                f"location.href='{FEED_URL}';"
                                "}, 100)</script>Sign in"
                            ),
                        )
                    else:
                        route.fulfill(content_type="text/html", body="Page ready")

                context.route("https://www.linkedin.com/**", route_request)
                session = TangoBrowserSession(page, _context=context)
                session.open_logged_in_tango(Event(), timeout=5)

                self.assertEqual(page.url, TANGO_URL)
                self.assertEqual(requests, [FEED_URL, "https://www.linkedin.com/login", FEED_URL, TANGO_URL])
            finally:
                browser.close()
