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
            # Add https:// if no protocol specified
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Wait a bit more for dynamic content
            await self.page.wait_for_load_state("networkidle", timeout=10000)
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
                "error": f"Navigation failed: {str(e)}"
            }

    async def click(self, selector: str) -> dict:
        """Click an element by selector."""
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        try:
            # Wait for selector to be visible and stable
            await self.page.wait_for_selector(selector, state="visible", timeout=15000)
            # Scroll into view if needed
            await self.page.evaluate(f"""
                const el = document.querySelector('{selector}');
                if (el) el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            """)
            await self.page.wait_for_timeout(500)  # Small delay for scroll
            await self.page.click(selector)
            return {"status": "success", "selector": selector}
        except Exception as e:
            # Try to find alternative selectors
            error_msg = str(e)
            suggestions = await self._suggest_selectors(selector)
            return {
                "status": "error",
                "error": f"Selector not found: {error_msg}",
                "selector": selector,
                "suggestions": suggestions
            }

    async def type_text(self, selector: str, text: str) -> dict:
        """Type text into an input field."""
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        try:
            # Wait for selector with multiple strategies
            await self.page.wait_for_selector(selector, state="visible", timeout=15000)
            
            # Try to find the element and check if it's an input
            element = await self.page.query_selector(selector)
            if not element:
                raise Exception(f"Element with selector '{selector}' not found")
            
            # Clear existing value first
            await self.page.fill(selector, "")
            # Type the text
            await self.page.type(selector, text, delay=50)
            
            return {"status": "success", "selector": selector, "text": text}
        except Exception as e:
            error_msg = str(e)
            # Try alternative selectors for common search inputs
            alternatives = [
                "input[type='search']",
                "input[type='text']",
                "input",
                "textarea",
                "[role='searchbox']",
                "#search",
                ".search-input"
            ]
            
            suggestions = await self._suggest_selectors(selector)
            
            return {
                "status": "error",
                "error": f"Selector not found: {error_msg}",
                "selector": selector,
                "suggestions": suggestions,
                "alternatives": alternatives[:3]  # Show first 3 alternatives
            }

    async def wait_for(self, selector: str, timeout: int = 5000) -> dict:
        """Wait for an element to appear."""
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        try:
            await self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            return {"status": "success", "selector": selector}
        except Exception as e:
            suggestions = await self._suggest_selectors(selector)
            return {
                "status": "error",
                "error": f"Element not found within timeout: {str(e)}",
                "selector": selector,
                "suggestions": suggestions
            }
    
    async def _suggest_selectors(self, original_selector: str) -> list:
        """Suggest alternative selectors if the original fails."""
        if not self.page:
            return []
        
        try:
            # Get all input elements on the page
            inputs = await self.page.evaluate("""
                () => {
                    const inputs = Array.from(document.querySelectorAll('input, textarea, [contenteditable="true"]'));
                    return inputs.slice(0, 5).map(el => ({
                        tag: el.tagName.toLowerCase(),
                        type: el.type || 'text',
                        name: el.name || '',
                        id: el.id || '',
                        placeholder: el.placeholder || '',
                        className: el.className || ''
                    }));
                }
            """)
            
            suggestions = []
            for inp in inputs:
                if inp['id']:
                    suggestions.append(f"#{inp['id']}")
                if inp['name']:
                    suggestions.append(f"{inp['tag']}[name='{inp['name']}']")
                if inp['placeholder']:
                    suggestions.append(f"{inp['tag']}[placeholder*='{inp['placeholder'][:20]}']")
            
            return list(set(suggestions))[:5]  # Return unique suggestions, max 5
        except:
            return []

    async def extract(self, schema: dict, limit: int = None) -> dict:
        """Extract data from page using CSS selectors.
        
        Schema format: {"field_name": "css_selector"}
        Returns structured data with arrays for each field.
        """
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        try:
            result = await self.page.evaluate("""
                (schema, limit) => {
                    const data = {};
                    for (const [key, selector] of Object.entries(schema)) {
                        const elements = document.querySelectorAll(selector);
                        if (elements.length > 0) {
                            let values = Array.from(elements).map(el => el.textContent?.trim() || '');
                            if (limit && limit > 0) {
                                values = values.slice(0, limit);
                            }
                            data[key] = values;
                        } else {
                            data[key] = [];
                        }
                    }
                    return data;
                }
            """, schema, limit or 0)
            
            # Transform to list of objects if multiple fields
            if result and len(result) > 0:
                field_names = list(result.keys())
                max_length = max(len(result[field]) for field in field_names) if result else 0
                
                # Create list of objects
                structured = []
                for i in range(max_length):
                    item = {}
                    for field in field_names:
                        item[field] = result[field][i] if i < len(result[field]) else None
                    structured.append(item)
                
                return {
                    "status": "success",
                    "data": structured,
                    "count": len(structured)
                }
            
            return {
                "status": "success",
                "data": [],
                "count": 0
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

# Global instance
browser_agent = BrowserAgent()

