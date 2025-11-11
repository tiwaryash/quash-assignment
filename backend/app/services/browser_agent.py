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
        """Click an element by selector with automatic fallback."""
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        # List of selectors to try
        selectors_to_try = [selector]
        
        # If it's a submit button, try common alternatives
        if "button[type='submit']" in selector or "submit" in selector.lower():
            selectors_to_try.extend([
                "input[name='btnK']",  # Google search button
                "input[type='submit']",
                "button:has-text('Search')",
                "button[aria-label*='Search']",
                "button[aria-label*='search']",
                "[role='button']:has-text('Search')"
            ])
        elif "button" in selector:
            # Try to find button by text if it's a generic button selector
            selectors_to_try.extend([
                "input[type='submit']",
                "[role='button']"
            ])
        
        # Try each selector
        last_error = None
        for sel in selectors_to_try:
            try:
                await self.page.wait_for_selector(sel, state="visible", timeout=5000)
                # Scroll into view if needed
                await self.page.evaluate(f"""
                    const el = document.querySelector('{sel}');
                    if (el) el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                """)
                await self.page.wait_for_timeout(500)
                await self.page.click(sel)
                return {
                    "status": "success", 
                    "selector": sel,
                    "original_selector": selector if sel != selector else None
                }
            except Exception as e:
                last_error = str(e)
                continue
        
        # If all failed, get suggestions
        suggestions = await self._suggest_selectors(selector)
        return {
            "status": "error",
            "error": f"Selector not found: {last_error}",
            "selector": selector,
            "suggestions": suggestions,
            "tried_selectors": selectors_to_try[:5]
        }

    async def type_text(self, selector: str, text: str) -> dict:
        """Type text into an input field with automatic fallback to alternatives."""
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        # List of selectors to try in order
        selectors_to_try = [selector]
        
        # If the original selector is input[name='q'], add textarea alternative (common for Google, etc.)
        if "input[name='q']" in selector:
            selectors_to_try.extend([
                "textarea[name='q']",
                "#APjFqb",  # Google's search box ID
                "textarea",
                "input[type='search']",
                "[role='searchbox']"
            ])
        elif "input" in selector and "textarea" not in selector:
            # If it's an input selector, also try textarea
            textarea_version = selector.replace("input", "textarea")
            selectors_to_try.append(textarea_version)
            selectors_to_try.extend([
                "textarea[name='q']",
                "input[type='search']",
                "[role='searchbox']"
            ])
        
        # Try each selector until one works
        last_error = None
        for sel in selectors_to_try:
            try:
                await self.page.wait_for_selector(sel, state="visible", timeout=5000)
                element = await self.page.query_selector(sel)
                if element:
                    # Clear existing value first
                    await self.page.fill(sel, "")
                    # Type the text
                    await self.page.type(sel, text, delay=50)
                    return {
                        "status": "success", 
                        "selector": sel, 
                        "text": text,
                        "original_selector": selector if sel != selector else None
                    }
            except Exception as e:
                last_error = str(e)
                continue
        
        # If all selectors failed, get suggestions
        suggestions = await self._suggest_selectors(selector)
        
        return {
            "status": "error",
            "error": f"Selector not found: {last_error}",
            "selector": selector,
            "suggestions": suggestions,
            "tried_selectors": selectors_to_try[:5]  # Show what we tried
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

