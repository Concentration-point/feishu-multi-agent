from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = BASE_DIR / 'data' / 'snapshots'


async def run_signup(email: str, headless: bool = False, proxy: str | None = None):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    launch_args = {}
    if proxy:
        launch_args['proxy'] = {'server': proxy}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, **launch_args)
        context = await browser.new_context()
        page = await context.new_page()
        result = {
            'ok': False,
            'stage': 'launch',
            'email': email,
            'observations': [],
            'checked_at': datetime.now().isoformat(),
        }
        try:
            await page.goto('https://auth.openai.com/', wait_until='domcontentloaded', timeout=45000)
            result['stage'] = 'open_auth'
            result['observations'].append('opened_auth_page')

            try:
                await page.get_by_role('button', name=re.compile('sign up', re.I)).click(timeout=8000)
                result['observations'].append('clicked_sign_up_button')
            except Exception:
                result['observations'].append('sign_up_button_not_found_directly')

            try:
                await page.get_by_placeholder(re.compile('email', re.I)).fill(email, timeout=10000)
                result['observations'].append('filled_email_placeholder')
            except Exception:
                try:
                    await page.locator('input[type="email"]').fill(email, timeout=10000)
                    result['observations'].append('filled_email_input')
                except Exception as e:
                    result['stage'] = 'fill_email_failed'
                    result['error'] = str(e)
                    await page.screenshot(path=str(STATE_DIR / 'openai-signup-fill-email-failed.png'), full_page=True)
                    return result

            await page.screenshot(path=str(STATE_DIR / 'openai-signup-after-email.png'), full_page=True)
            result['stage'] = 'email_filled'
            result['ok'] = True
            return result
        except PlaywrightTimeoutError as e:
            result['stage'] = 'timeout'
            result['error'] = str(e)
            await page.screenshot(path=str(STATE_DIR / 'openai-signup-timeout.png'), full_page=True)
            return result
        finally:
            await context.close()
            await browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--email', required=True)
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--proxy', default='')
    args = parser.parse_args()
    result = asyncio.run(run_signup(email=args.email, headless=args.headless, proxy=args.proxy or None))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    import re
    main()
