import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


async def capture(base_url: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={"width": 1366, "height": 900})
        page = await context.new_page()

        scenarios = [
            ("home.png", "/"),
            ("search.png", "/search?query=test"),
            ("stats.png", "/stats"),
        ]

        for filename, path in scenarios:
            url = base_url.rstrip("/") + path
            await page.goto(url, wait_until="networkidle")
            await page.screenshot(path=str(out_dir / filename), full_page=True)

        await context.close()
        await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture UI screenshots")
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument(
        "--out",
        default=str(Path("web/static/images/screenshots")),
        help="Output directory for screenshots",
    )
    args = parser.parse_args()

    asyncio.run(capture(args.base_url, Path(args.out)))


if __name__ == "__main__":
    main()
