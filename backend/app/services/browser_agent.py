from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import asyncio

class BrowserAgent:
    def __init__(self):
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.playwright = None

    async def start(self):
        """Initialize browser instance."""
        if self.browser is None:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()

    async def close(self):
        """Close browser instance."""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.browser = None
        self.context = None
        self.page = None

    async def navigate(self, url: str) -> dict:
        """Navigate to a URL."""
        if not self.page:
            await self.start()
        
        try:
            await self.page.goto(url, wait_until="networkidle", timeout=30000)
            current_url = self.page.url
            title = await self.page.title()
            return {
                "status": "success",
                "url": current_url,
                "title": title
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    async def click(self, selector: str) -> dict:
        """Click an element by selector."""
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        try:
            await self.page.wait_for_selector(selector, timeout=10000)
            await self.page.click(selector)
            return {"status": "success", "selector": selector}
        except Exception as e:
            return {
                "status": "error",
                "error": f"Selector not found or clickable: {str(e)}",
                "selector": selector
            }

    async def type_text(self, selector: str, text: str) -> dict:
        """Type text into an input field."""
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        try:
            await self.page.wait_for_selector(selector, timeout=10000)
            await self.page.fill(selector, text)
            return {"status": "success", "selector": selector, "text": text}
        except Exception as e:
            return {
                "status": "error",
                "error": f"Selector not found: {str(e)}",
                "selector": selector
            }

    async def wait_for(self, selector: str, timeout: int = 5000) -> dict:
        """Wait for an element to appear."""
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            return {"status": "success", "selector": selector}
        except Exception as e:
            return {
                "status": "error",
                "error": f"Element not found within timeout: {str(e)}",
                "selector": selector
            }

    async def extract(self, schema: dict) -> dict:
        """Extract data from page using CSS selectors."""
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        try:
            result = await self.page.evaluate("""
                (schema) => {
                    const data = {};
                    for (const [key, selector] of Object.entries(schema)) {
                        const elements = document.querySelectorAll(selector);
                        if (elements.length > 0) {
                            data[key] = Array.from(elements).map(el => el.textContent?.trim() || '');
                        } else {
                            data[key] = [];
                        }
                    }
                    return data;
                }
            """, schema)
            
            return {
                "status": "success",
                "data": result
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

# Global instance
browser_agent = BrowserAgent()

