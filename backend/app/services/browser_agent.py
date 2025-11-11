from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from app.services.site_selectors import get_selectors_for_site, detect_site_from_url
import asyncio

class BrowserAgent:
    def __init__(self):
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.playwright = None
        self.current_site: str = "generic"  # Track current site for selector strategies

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
        """Navigate to a URL and detect the site type."""
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
            
            # Detect site type for better selector strategies
            self.current_site = detect_site_from_url(current_url)
            
            return {
                "status": "success",
                "url": current_url,
                "title": title,
                "site": self.current_site
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
            # Add site-specific search button selectors
            site_selectors = get_selectors_for_site(self.current_site)
            selectors_to_try.extend(site_selectors.get("search_button", [])[:3])
            selectors_to_try.extend([
                "input[name='btnK']",  # Google search button
                "input[type='submit']",
                "input[value='Google Search']",
                "input[value='Search']",
                "button[aria-label*='Search']",
                "button[aria-label*='search']"
            ])
        
        # Remove duplicates while preserving order
        seen = set()
        selectors_to_try = [x for x in selectors_to_try if not (x in seen or seen.add(x))]
        
        if "button" in selector and "submit" not in selector.lower():
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
                # Scroll into view if needed - use proper escaping
                try:
                    await self.page.evaluate("""
                        (selector) => {
                            const el = document.querySelector(selector);
                            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        }
                    """, sel)
                except:
                    pass  # If scroll fails, continue anyway
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
        
        # Get site-specific selectors if available
        site_selectors = get_selectors_for_site(self.current_site)
        if selector not in site_selectors.get("search_input", []):
            # Add site-specific search input selectors
            selectors_to_try.extend(site_selectors.get("search_input", [])[:3])
        
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
        
        # Remove duplicates while preserving order
        seen = set()
        selectors_to_try = [x for x in selectors_to_try if not (x in seen or seen.add(x))]
        
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
            # Pass schema and limit as a single object to avoid argument count issues
            result = await self.page.evaluate("""
                ({schema, limit}) => {
                    const data = {};
                    for (const [key, selector] of Object.entries(schema)) {
                        const elements = document.querySelectorAll(selector);
                        if (elements.length > 0) {
                            let values = [];
                            if (key === 'link' || key === 'url') {
                                // For links, get href attribute
                                values = Array.from(elements).map(el => {
                                    const href = el.href || el.getAttribute('href') || '';
                                    return href.startsWith('http') ? href : (window.location.origin + href);
                                });
                            } else {
                                // For text content
                                values = Array.from(elements).map(el => el.textContent?.trim() || '');
                            }
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
            """, {"schema": schema, "limit": limit or 0})
            
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

