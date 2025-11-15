from playwright.async_api import async_playwright, Page, Browser, BrowserContext, TimeoutError as PlaywrightTimeout
from app.services.site_selectors import get_selectors_for_site, detect_site_from_url
from app.services.site_handlers import GoogleMapsHandler, SiteExtractionHandler, YouTubeHandler, GoogleSearchHandler
from app.core.config import settings
from app.core.retry import retry_async, RetryConfig
from app.core.logger import logger, log_action
from app.core.llm_provider import get_llm_provider
import asyncio
import json
import random
import string
import urllib.parse
from typing import List, Dict, Optional

class BrowserAgent:
    def __init__(self):
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.playwright = None
        self.current_site: str = "generic"  # Track current site for selector strategies
        self._retry_config = RetryConfig(max_retries=3, initial_delay=1.0, exponential_base=2.0)

    async def start(self, use_stealth: bool = False):
        """Initialize browser instance with error handling and optional stealth mode.
        
        Args:
            use_stealth: If True, enable stealth mode with enhanced anti-detection measures
        """
        if self.browser is None:
            try:
                self.playwright = await async_playwright().start()
                
                # Enhanced browser args for stealth mode
                browser_args = [
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                ]
                
                if use_stealth:
                    # Additional stealth args
                    browser_args.extend([
                        '--disable-web-security',
                        '--disable-features=IsolateOrigins,site-per-process',
                        '--disable-site-isolation-trials',
                        '--disable-features=BlockInsecurePrivateNetworkRequests',
                    ])
                
                self.browser = await self.playwright.chromium.launch(
                    headless=settings.headless,
                    args=browser_args
                )
            except Exception as e:
                logger.error(f"Failed to start browser: {e}")
                raise
            
            # Create context with realistic browser settings
            context_options = {
                'viewport': {'width': 1920, 'height': 1080},
                'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'locale': 'en-IN',
                'timezone_id': 'Asia/Kolkata',
                'extra_http_headers': {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            }
            
            # Add permissions for file access in stealth mode
            if use_stealth:
                context_options['bypass_csp'] = True
                context_options['ignore_https_errors'] = True
            
            self.context = await self.browser.new_context(**context_options)
            
            # Enhanced stealth script to bypass detection
            stealth_script = """
                // Remove webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Override the `plugins` property to use a custom getter
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // Override the `languages` property
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                
                // Mock chrome object
                window.chrome = {
                    runtime: {}
                };
                
                // Override permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """
            
            await self.context.add_init_script(stealth_script)
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
            # Add https:// if no protocol specified (but not for file:// or other protocols)
            if not url.startswith(('http://', 'https://', 'file://', 'about:', 'data:')):
                url = 'https://' + url
            
            # Detect if this is Google Maps - it needs special handling
            is_google_maps = "maps.google" in url.lower() or "google.com/maps" in url.lower()
            
            # Try navigation with retry for network errors
            max_retries = 2
            last_error = None
            for attempt in range(max_retries):
                try:
                    
                    # For Google Maps, use "load" instead of "domcontentloaded" and skip networkidle
                    if is_google_maps:
                        await self.page.goto(url, wait_until="load", timeout=30000)
                        # Google Maps is a heavy SPA that never reaches networkidle
                        # Wait for the search box to appear instead
                        try:
                            # Wait for search input to appear (indicates page is ready)
                            await self.page.wait_for_selector('input[aria-label*="Search"], input[placeholder*="Search"], input#searchboxinput', timeout=15000, state="visible")
                        except Exception as wait_error:
                            # Even if search box doesn't appear, wait a bit for page to settle
                            await asyncio.sleep(3)
                    else:
                        # For other sites, use standard strategy
                        await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        # Wait a bit more for dynamic content, but with shorter timeout for heavy sites
                        try:
                            await self.page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception as networkidle_error:
                            # For heavy sites, networkidle might never happen, but page is still usable
                            await asyncio.sleep(2)  # Give it a moment anyway
                    
                    break  # Success, exit retry loop
                except Exception as e:
                    last_error = e
                    error_str = str(e)
                    
                    # Check if it's a network error that might be retryable
                    if "ERR_HTTP2_PROTOCOL_ERROR" in error_str or "net::" in error_str:
                        if attempt < max_retries - 1:
                            # Wait a bit before retry
                            await asyncio.sleep(2)
                            continue
                    # Check if it's just a timeout (not a critical error for heavy sites)
                    if "Timeout" in error_str and is_google_maps:
                        # Try to check if page loaded anyway
                        try:
                            current_url_check = self.page.url
                            if current_url_check and "maps" in current_url_check.lower():
                                break
                        except:
                            pass
                    
                    # If not retryable or last attempt, raise
                    if attempt == max_retries - 1:
                        raise
            
            current_url = self.page.url
            title = await self.page.title()
            
            # Check for CAPTCHA or blocking pages
            captcha_detected = await self._detect_captcha()
            if captcha_detected:
                return {
                    "status": "blocked",
                    "url": current_url,
                    "title": title,
                    "block_type": "captcha",
                    "message": "Google has detected automated access and is showing a CAPTCHA. This is common when scraping Google search results.",
                    "alternatives": [
                        "Try using Zomato or Swiggy for local discovery instead",
                        "Use a different search engine",
                        "Wait a few minutes and try again"
                    ]
                }
            
            # Detect site type for better selector strategies
            self.current_site = detect_site_from_url(current_url)
            
            return {
                "status": "success",
                "url": current_url,
                "title": title,
                "site": self.current_site
            }
        except Exception as e:
            error_str = str(e)
            # Provide helpful error messages
            if "ERR_HTTP2_PROTOCOL_ERROR" in error_str:
                # Check if it's Zomato or Swiggy - suggest Google Maps as alternative
                url_lower = url.lower()
                suggestions = [
                    "Try again in a few moments",
                    "The site might be temporarily unavailable"
                ]
                
                if "zomato" in url_lower or "swiggy" in url_lower:
                    suggestions.append("Zomato/Swiggy may be blocking automated access")
                    suggestions.append("Try using Google Maps instead for local discovery")
                    suggestions.append("You can search 'pizza places in [location]' on Google Maps")
                
                return {
                    "status": "error",
                    "error": f"Network error connecting to {url}. This might be a temporary network issue or the site might be blocking automated access.",
                    "suggestions": suggestions,
                    "retryable": True,
                    "alternative": "google_maps" if ("zomato" in url_lower or "swiggy" in url_lower) else None
                }
            elif "net::" in error_str:
                return {
                    "status": "error",
                    "error": f"Network error: {error_str}",
                    "suggestions": [
                        "Check your internet connection",
                        "The site might be temporarily unavailable",
                        "Try again in a few moments"
                    ],
                    "retryable": True
                }
            elif "Timeout" in error_str:
                # For timeout errors, check if we're on Google Maps
                if "maps.google" in url.lower():
                    return {
                        "status": "error",
                        "error": f"Timeout loading Google Maps. The page may still be usable, but some features might not be ready.",
                        "suggestions": [
                            "Google Maps is a heavy application and may take time to load",
                            "Try the search anyway - the page might be ready",
                            "Wait a moment and retry"
                        ],
                        "retryable": True,
                        "partial_success": True  # Indicate page might still be usable
                    }
                else:
                    return {
                        "status": "error",
                        "error": f"Navigation timeout: {error_str}",
                        "suggestions": [
                            "The page might be taking too long to load",
                            "Try again in a few moments",
                            "Check if the site is accessible"
                        ],
                        "retryable": True
                    }
            else:
                return {
                    "status": "error",
                    "error": f"Navigation failed: {error_str}",
                    "debug_info": f"Exception type: {type(e).__name__}"
                }
    
    async def _detect_captcha(self) -> bool:
        """Detect if the current page is a CAPTCHA or blocking page."""
        if not self.page:
            return False
        
        try:
            current_url = self.page.url
            
            # Check URL for CAPTCHA indicators
            if "/sorry/" in current_url or "/sorry/index" in current_url:
                return True
            
            # Check for common CAPTCHA elements
            captcha_selectors = [
                "#g-recaptcha-response",
                "iframe[src*='recaptcha']",
                ".g-recaptcha",
                "[data-sitekey]",  # reCAPTCHA site key
                "text=unusual traffic",
                "text=automated queries"
            ]
            
            for selector in captcha_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        return True
                except:
                    continue
            
            # Check page content for CAPTCHA indicators
            page_text = await self.page.evaluate("() => document.body.innerText.toLowerCase()")
            captcha_keywords = [
                "unusual traffic",
                "automated queries",
                "captcha",
                "verify you're not a robot",
                "sorry, we have detected"
            ]
            
            if any(keyword in page_text for keyword in captcha_keywords):
                return True
            
            return False
        except:
            return False

    async def search_google_maps(self, query: str, limit: int = 5, lat: float = 12.9250, lng: float = 77.6400) -> Dict:
        """
        Search Google Maps for `query` near given lat/lng (defaults to HSR Layout, Bangalore) and extract results.
        This is a robust, battle-tested function that handles Maps' async rendering and common issues.
        
        Returns: {"status":"success","data":[{name, rating, address, url}], "diagnostic": {...}}
        """
        if not self.page:
            await self.start()
        
        return await GoogleMapsHandler.search(self.page, self.context, query, limit, lat, lng)

    async def click(self, selector: str) -> dict:
        """Click an element by selector with automatic fallback."""
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        # For Google Maps, if clicking a submit button, try pressing Enter on the search input instead
        if self.current_site == "google_maps" and ("submit" in selector.lower() or "button" in selector.lower()):
            # Try to find the search input and press Enter
            try:
                search_input = await self.page.query_selector("input#searchboxinput, input[aria-label*='Search']")
                if search_input:
                    current_url = self.page.url
                    await self.page.keyboard.press("Enter")
                    
                    # Wait for URL to change (indicates search executed)
                    try:
                        await self.page.wait_for_url(lambda url: url != current_url, timeout=10000)
                    except:
                        pass
                    
                    # Wait longer for Google Maps to load results
                    await self.page.wait_for_timeout(5000)  # Increased wait time for Google Maps
                    
                    # Check if results appeared
                    try:
                        await self.page.wait_for_selector(".Nv2PK, [role='article'], [data-result-index]", state="attached", timeout=5000)
                    except:
                        pass
                    
                    return {
                        "status": "success",
                        "selector": "input#searchboxinput (pressed Enter)",
                        "original_selector": selector,
                        "method": "keyboard_enter",
                        "note": "Google Maps search executed, results may take time to load"
                    }
            except Exception as e:
                # Fall through to normal click handling
                pass
        
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
        
        # For Google Maps, prioritize the searchboxinput selector
        if self.current_site == "google_maps":
            if "input#searchboxinput" not in selectors_to_try:
                selectors_to_try.insert(0, "input#searchboxinput")
            # Also add other Maps-specific selectors
            if "input[aria-label*='Search']" not in selectors_to_try:
                selectors_to_try.insert(1, "input[aria-label*='Search']")
        
        # For YouTube, add YouTube-specific selectors
        if self.current_site == "youtube":
            youtube_selectors = [
                "input[name='search_query']",
                "#search",
                "input#search",
                "input[placeholder*='Search']",
                "input[aria-label*='Search']"
            ]
            for yt_sel in youtube_selectors:
                if yt_sel not in selectors_to_try:
                    selectors_to_try.insert(0, yt_sel)
        
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
                    
                    # For Google Maps, automatically press Enter after typing
                    if self.current_site == "google_maps":
                        await asyncio.sleep(0.5)  # Small delay to ensure typing is complete
                        await self.page.keyboard.press("Enter")
                        
                        # Wait for URL to change (search executed)
                        current_url = self.page.url
                        try:
                            await self.page.wait_for_url(lambda url: url != current_url, timeout=8000)
                        except:
                            pass
                        
                        # Wait for results to load - Google Maps needs much more time
                        
                        # Poll for results over time instead of just waiting
                        max_wait = 15  # seconds
                        poll_interval = 2  # seconds
                        result_count = 0
                        
                        for i in range(0, max_wait, poll_interval):
                            await asyncio.sleep(poll_interval)
                            result_count = await self.page.evaluate("""
                                () => {
                                    // Try multiple strategies to find results
                                    let count = 0;
                                    count = Math.max(count, document.querySelectorAll('div[role="article"]').length);
                                    count = Math.max(count, document.querySelectorAll('[data-result-index]').length);
                                    const h3s = document.querySelectorAll('h3');
                                    count = Math.max(count, h3s.length);
                                    
                                    // Also try finding any divs with ratings
                                    const withRatings = document.querySelectorAll('[aria-label*="star"]');
                                    count = Math.max(count, withRatings.length);
                                    
                                    return count;
                                }
                            """)
                            
                            
                            if result_count >= 3:  # If we found at least 3 results, stop polling
                                break
                        
                        # Get page structure info for debugging
                        page_info = await self.page.evaluate("""
                            () => {
                                const allDivs = document.querySelectorAll('div');
                                const allH3s = document.querySelectorAll('h3');
                                return {
                                    totalDivs: allDivs.length,
                                    totalH3s: allH3s.length,
                                    sampleH3Text: Array.from(allH3s).slice(0, 5).map(h3 => h3.textContent?.trim()),
                                    hasResults: document.querySelector('#pane') !== null,
                                    hasSidebar: document.querySelector('[role="main"]') !== null
                                };
                            }
                        """)
                        
                        return {
                            "status": "success", 
                            "selector": sel, 
                            "text": text,
                            "original_selector": selector if sel != selector else None,
                            "note": "Search submitted automatically on Google Maps"
                        }
                    
                    # For YouTube, automatically press Enter after typing (no need for click)
                    elif self.current_site == "youtube":
                        await asyncio.sleep(0.5)  # Small delay to ensure typing is complete
                        await self.page.keyboard.press("Enter")
                        
                        # Wait for URL to change (search executed) or results to appear
                        current_url = self.page.url
                        try:
                            await self.page.wait_for_url(lambda url: url != current_url or "results" in url.lower() or "search_query" in url.lower(), timeout=10000)
                        except:
                            pass
                        
                        # Wait a bit for results to load
                        await asyncio.sleep(2)
                        
                        return {
                            "status": "success", 
                            "selector": sel, 
                            "text": text,
                            "original_selector": selector if sel != selector else None,
                            "note": "Search submitted automatically on YouTube (Enter pressed)"
                        }
                    
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
        
        # Check for CAPTCHA before waiting
        captcha_detected = await self._detect_captcha()
        if captcha_detected:
            return {
                "status": "blocked",
                "error": "Page is blocked by CAPTCHA. Cannot proceed with automation.",
                "selector": selector,
                "block_type": "captcha",
                "message": "Google has detected automated access. Consider using alternative sites like Zomato or Swiggy for local discovery."
            }
        
        # For Google Maps, use smarter detection - wait for h3 elements as indicators
        if self.current_site == "google_maps":
            
            # First, wait a bit for page to settle after search
            await asyncio.sleep(2)
            
            # Check if results are already present by looking for h3 elements (result names)
            try:
                h3_count = await self.page.evaluate("() => document.querySelectorAll('h3').length")
                if h3_count >= 3:  # If we have at least 3 h3s, likely results are there
                    # Also check if we can find rating elements
                    rating_count = await self.page.evaluate("() => document.querySelectorAll('[aria-label*=\"star\"]').length")
                    return {"status": "success", "selector": "h3 (indicator)", "original_selector": selector, "note": f"Results detected via h3 count ({h3_count} found)"}
            except Exception as e:
                pass
            
            # If it's a name/rating/location selector or container selector, wait for containers
            container_selectors = [
                "h3",  # Names are usually in h3 - use as primary indicator
                "[data-result-index]",
                "div[role='article']",
                "[class*='section-result']",
                ".Nv2PK",
                "[aria-label*='star']"  # Rating elements also indicate results
            ]
            
            container_found = False
            found_selector = None
            
            for container_sel in container_selectors:
                try:
                    # Use a reasonable timeout per selector
                    await self.page.wait_for_selector(container_sel, state="visible", timeout=max(3000, timeout // len(container_selectors)))
                    count = await self.page.evaluate(f"() => document.querySelectorAll('{container_sel}').length")
                    if count > 0:
                        container_found = True
                        found_selector = container_sel
                        # Wait a bit more for individual elements to render
                        await asyncio.sleep(1)
                        break
                except Exception as e:
                    continue
            
            if container_found:
                # If we were waiting for a specific element, try to find it
                if selector not in container_selectors and selector != "h3":
                    try:
                        await self.page.wait_for_selector(selector, state="visible", timeout=3000)
                        return {"status": "success", "selector": selector}
                    except:
                        # Even if specific element not found, containers exist, so continue
                        return {"status": "success", "selector": found_selector or "h3 (fallback)", "original_selector": selector, "note": "Containers found but specific element may not be visible yet"}
                else:
                    return {"status": "success", "selector": found_selector or selector}
        
        try:
            await self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            return {"status": "success", "selector": selector}
        except Exception as e:
            # Check if we got redirected to CAPTCHA during wait
            captcha_detected = await self._detect_captcha()
            if captcha_detected:
                return {
                    "status": "blocked",
                    "error": "Page redirected to CAPTCHA during wait",
                    "selector": selector,
                    "block_type": "captcha",
                    "message": "Google blocked the request. Try using Zomato or Swiggy instead for local discovery."
                }
            
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

    async def analyze_form(self, user_instruction: str = "") -> dict:
        """Analyze form on the page and determine what fields to fill using LLM.
        
        This function automatically waits for form fields to appear, so no wait_for is needed before calling it.
        
        Returns: {
            "status": "success",
            "fields": {
                "field_name": {
                    "selector": "css_selector",
                    "value": "generated_value",
                    "type": "email|password|text|etc"
                }
            }
        }
        """
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        try:
            # Automatically wait for form fields to appear (no need for separate wait_for action)
            # Try common form field selectors
            form_field_selectors = [
                "input[type='email']",
                "input[type='text']",
                "input[type='password']",
                "input[name*='email']",
                "input[name*='name']",
                "form input",
                "form textarea",
                "form select"
            ]
            
            form_found = False
            for selector in form_field_selectors:
                try:
                    await self.page.wait_for_selector(selector, state="visible", timeout=5000)
                    form_found = True
                    break
                except:
                    continue
            
            # If no specific field found, wait a bit for page to settle
            if not form_found:
                await asyncio.sleep(2)
            
            # Extract form structure from the page
            form_data = await self.page.evaluate("""
                () => {
                    const forms = Array.from(document.querySelectorAll('form'));
                    if (forms.length === 0) {
                        // If no form tag, look for form-like structures
                        const inputs = Array.from(document.querySelectorAll('input, textarea, select'));
                        if (inputs.length > 0) {
                            return {
                                hasFormTag: false,
                                fields: inputs.map((el, idx) => ({
                            index: idx,
                            tag: el.tagName.toLowerCase(),
                            type: el.type || 'text',
                            name: el.name || '',
                            id: el.id || '',
                            placeholder: el.placeholder || '',
                            value_attr: el.getAttribute('value') || '',
                            label: (() => {
                                // Try to find associated label
                                if (el.id) {
                                    const label = document.querySelector(`label[for="${el.id}"]`);
                                    if (label) return label.textContent?.trim() || '';
                                }
                                // Try to find label as parent or sibling
                                const parent = el.parentElement;
                                if (parent) {
                                    const label = parent.querySelector('label');
                                    if (label) return label.textContent?.trim() || '';
                                }
                                // Try previous sibling
                                let prev = el.previousElementSibling;
                                if (prev && prev.tagName.toLowerCase() === 'label') {
                                    return prev.textContent?.trim() || '';
                                }
                                // Try next sibling (for checkboxes/radios often come after)
                                let next = el.nextElementSibling;
                                if (next && next.tagName.toLowerCase() === 'label') {
                                    return next.textContent?.trim() || '';
                                }
                                return '';
                            })(),
                            required: el.hasAttribute('required') || el.getAttribute('aria-required') === 'true',
                            pattern: el.getAttribute('pattern') || '',
                            autocomplete: el.getAttribute('autocomplete') || '',
                            className: el.className || '',
                            value: el.value || '',
                            checked: el.checked || false
                        }))
                            };
                        }
                    }
                    
                    // Process forms
                    const form = forms[0]; // Use first form
                    const inputs = Array.from(form.querySelectorAll('input, textarea, select'));
                    
                    return {
                        hasFormTag: true,
                        formAction: form.action || '',
                        formMethod: form.method || 'get',
                        fields: inputs.map((el, idx) => ({
                            index: idx,
                            tag: el.tagName.toLowerCase(),
                            type: el.type || 'text',
                            name: el.name || '',
                            id: el.id || '',
                            placeholder: el.placeholder || '',
                            value_attr: el.getAttribute('value') || '',
                            label: (() => {
                                if (el.id) {
                                    const label = document.querySelector(`label[for="${el.id}"]`);
                                    if (label) return label.textContent?.trim() || '';
                                }
                                const parent = el.parentElement;
                                if (parent) {
                                    const label = parent.querySelector('label');
                                    if (label) return label.textContent?.trim() || '';
                                }
                                let prev = el.previousElementSibling;
                                if (prev && prev.tagName.toLowerCase() === 'label') {
                                    return prev.textContent?.trim() || '';
                                }
                                let next = el.nextElementSibling;
                                if (next && next.tagName.toLowerCase() === 'label') {
                                    return next.textContent?.trim() || '';
                                }
                                return '';
                            })(),
                            required: el.hasAttribute('required') || el.getAttribute('aria-required') === 'true',
                            pattern: el.getAttribute('pattern') || '',
                            autocomplete: el.getAttribute('autocomplete') || '',
                            className: el.className || '',
                            value: el.value || '',
                            checked: el.checked || false
                        }))
                    };
                }
            """)
            
            if not form_data or not form_data.get("fields") or len(form_data["fields"]) == 0:
                return {
                    "status": "error",
                    "error": "No form fields found on the page"
                }
            
            # Use LLM to determine what values to fill
            try:
                llm_provider = get_llm_provider()
            except Exception as e:
                logger.error(f"Failed to initialize LLM provider for form analysis: {e}")
                return {"status": "error", "error": "LLM provider not configured"}
            
            # Build prompt for LLM
            fields_description = json.dumps(form_data["fields"], indent=2)
            
            prompt = f"""Analyze this form structure and determine what values to fill for each field.

User instruction: {user_instruction}

Form fields found on the page:
{fields_description}

For each field, determine:
1. A CSS selector to target it (prefer id, then name, then other attributes)
2. An appropriate value to fill (generate temporary email if needed, realistic names, etc.)
3. The field type (email, password, text, select, tel, etc.)

IMPORTANT:
- For email fields, generate a temporary email like: temp_123456@example.com (use random numbers)
- For password fields, generate a secure password like: TempPass1234! (use random numbers and special chars)
- For confirm password fields, use the SAME password as the password field
- For name fields, use realistic names (e.g., "John Smith", "Jane Doe")
- For phone fields, use a valid format (e.g., "+1-555-123-4567" or "9876543210")
- For select/dropdown fields (tag='select'), provide a VALUE from the available options (not the display text)
- For required fields, always provide values
- Skip hidden fields (type='hidden')
- Skip submit buttons (type='submit' or type='button' with submit-like text)
- For date fields, use format YYYY-MM-DD (e.g., "1990-01-01")

CHECKBOX AND RADIO BUTTON HANDLING:
- For checkboxes (type='checkbox'), provide "true" to check or "false" to uncheck
- For radio buttons (type='radio'), you must include the value attribute in the selector
  * Example: If field has name="size" and value="medium", selector should be: input[name='size'][value='medium']
  * The value field in JSON should be "true" to select that radio button
- For checkbox groups (multiple checkboxes with same name), create separate entries for each checkbox
  * Each should have its own selector with the value attribute: input[name='topping'][value='bacon']
  * Set value to "true" to check, "false" to uncheck

SELECT FIELD HANDLING:
- If a field has tag='select', look at the field info to see if it contains options
- Provide the VALUE attribute of one of the options, not the display text
- Example: If options show <option value="USA">United States</option>, use "USA" not "United States"

Return JSON in this format:
{{
    "fields": {{
        "field_identifier": {{
            "selector": "css_selector",
            "value": "value_to_fill",
            "type": "email|password|text|select|tel|date|etc",
            "required": true|false
        }}
    }}
}}

Use field identifiers like: email, password, confirm_password, full_name, first_name, last_name, phone, country, etc.
For selectors, use the most reliable one: id > name > type+placeholder > className

EXAMPLES:
- Email field: {{"email": {{"selector": "#email", "value": "temp_784623@example.com", "type": "email"}}}}
- Password field: {{"password": {{"selector": "#password", "value": "SecurePass987!", "type": "password"}}}}
- Confirm password: {{"confirm_password": {{"selector": "#confirmPassword", "value": "SecurePass987!", "type": "password"}}}}
- Name field: {{"full_name": {{"selector": "#fullName", "value": "John Smith", "type": "text"}}}}
- Country select: {{"country": {{"selector": "#country", "value": "India", "type": "select"}}}}"""
            
            response_content = await llm_provider.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a form analysis assistant. Analyze forms and determine appropriate values to fill. Always return valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response_content)
            
            # Extract fields from LLM response
            analyzed_fields = result.get("fields", {})
            
            # Generate temporary email if needed
            temp_email = f"temp_{random.randint(100000, 999999)}@example.com"
            temp_password = f"TempPass{random.randint(1000, 9999)}!"
            
            # Post-process: ensure we have selectors and values
            final_fields = {}
            for field_id, field_info in analyzed_fields.items():
                selector = field_info.get("selector")
                value = field_info.get("value")
                field_type = field_info.get("type", "text")
                
                # If it's an email field and value is generic or missing, use temp email
                if field_type == "email":
                    if not value or "example.com" in str(value).lower() or "@" not in str(value):
                        value = temp_email
                
                # If it's a password field and value is generic or missing, use temp password
                if field_type == "password":
                    if not value or len(str(value)) < 6:
                        value = temp_password
                
                if selector and value:
                    final_fields[field_id] = {
                        "selector": selector,
                        "value": value,
                        "type": field_type
                    }
                elif selector:
                    # If we have a selector but no value, try to generate one based on type
                    if field_type == "email":
                        final_fields[field_id] = {
                            "selector": selector,
                            "value": temp_email,
                            "type": field_type
                        }
                    elif field_type == "password":
                        final_fields[field_id] = {
                            "selector": selector,
                            "value": temp_password,
                            "type": field_type
                        }
            
            return {
                "status": "success",
                "fields": final_fields,
                "form_structure": form_data
            }
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            return {
                "status": "error",
                "error": str(e),
                "traceback": error_trace
            }
    
    async def fill_form(self, fields: dict) -> dict:
        """Fill form fields dynamically with human-like behavior.
        
        fields format: {"field_name": {"selector": "css_selector", "value": "text", "type": "email|password|text"}}
        """
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        results = {}
        
        for field_name, field_info in fields.items():
            selector = field_info.get("selector")
            value = field_info.get("value")
            field_type = field_info.get("type", "text")
            
            if not selector or value is None:
                continue
            
            # Add random delay between fields to simulate human behavior
            await asyncio.sleep(random.uniform(0.3, 0.8))
            
            try:
                # Try to find and fill the field
                await self.page.wait_for_selector(selector, state="visible", timeout=5000)
                
                # Scroll field into view
                await self.page.evaluate(f"""
                    (selector) => {{
                        const el = document.querySelector(selector);
                        if (el) {{
                            el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        }}
                    }}
                """, selector)
                
                await asyncio.sleep(0.2)
                
                # Handle different field types
                if field_type == "select":
                    # For dropdown/select fields, use selectOption
                    await self.page.select_option(selector, str(value))
                    results[field_name] = {"status": "success", "selector": selector, "value": value, "type": "select"}
                    
                elif field_type == "checkbox" or field_type == "radio":
                    # For checkboxes and radio buttons, use check/click
                    # Value should be "true", "false", or specific radio value
                    value_str = str(value).lower()
                    
                    if field_type == "checkbox":
                        # For checkboxes, value is true/false
                        if value_str in ["true", "1", "yes", "on"]:
                            await self.page.check(selector)
                            results[field_name] = {"status": "success", "selector": selector, "value": value, "type": "checkbox", "checked": True}
                        else:
                            await self.page.uncheck(selector)
                            results[field_name] = {"status": "success", "selector": selector, "value": value, "type": "checkbox", "checked": False}
                    else:
                        # For radio buttons, click the option
                        await self.page.click(selector)
                        results[field_name] = {"status": "success", "selector": selector, "value": value, "type": "radio"}
                        
                else:
                    # For input fields (text, email, password, tel, etc.)
                    # Click the field to focus (human-like)
                    await self.page.click(selector)
                    await asyncio.sleep(0.1)
                    
                    # Clear the field first
                    await self.page.fill(selector, "")
                    
                    # Type with random delays to simulate human typing
                    for char in str(value):
                        await self.page.type(selector, char, delay=random.randint(30, 100))
                    
                    # Verify the value was set
                    filled_value = await self.page.input_value(selector)
                    if filled_value == str(value):
                        results[field_name] = {"status": "success", "selector": selector, "value": value}
                    else:
                        # If typing didn't work, try fill as fallback
                        await self.page.fill(selector, str(value))
                        results[field_name] = {"status": "success", "selector": selector, "value": value, "method": "fill"}
                    
            except Exception as e:
                # Try alternative selectors
                alternative_selectors = []
                
                # Generate alternative selectors based on field type
                if field_type == "email":
                    alternative_selectors = [
                        "input[type='email']",
                        "input[name*='email' i]",
                        "input[id*='email' i]",
                        "input[placeholder*='email' i]",
                        "input[autocomplete='email']"
                    ]
                elif field_type == "password":
                    alternative_selectors = [
                        "input[type='password']",
                        "input[name*='password' i]",
                        "input[id*='password' i]",
                        "input[autocomplete='current-password']",
                        "input[autocomplete='new-password']"
                    ]
                elif field_type == "text" or field_type == "tel":
                    # For name, phone, etc.
                    alternative_selectors = [
                        "input[type='text']",
                        "input[type='tel']",
                        f"input[name*='{field_name}' i]",
                        f"input[id*='{field_name}' i]"
                    ]
                
                # Try alternatives
                filled = False
                for alt_selector in alternative_selectors:
                    try:
                        await self.page.wait_for_selector(alt_selector, state="visible", timeout=2000)
                        await self.page.click(alt_selector)
                        await asyncio.sleep(0.1)
                        await self.page.fill(alt_selector, "")
                        
                        # Type with delays
                        for char in str(value):
                            await self.page.type(alt_selector, char, delay=random.randint(30, 100))
                        
                        results[field_name] = {
                            "status": "success", 
                            "selector": alt_selector, 
                            "value": value, 
                            "original_selector": selector
                        }
                        filled = True
                        break
                    except:
                        continue
                
                if not filled:
                    results[field_name] = {"status": "error", "error": str(e), "selector": selector}
        
        # Count successful fills
        success_count = sum(1 for r in results.values() if r.get("status") == "success")
        total_count = len(results)
        
        return {
            "status": "success" if success_count == total_count else ("partial" if success_count > 0 else "error"),
            "fields": results,
            "success_count": success_count,
            "total_count": total_count
        }
    
    async def submit_form(self, selector: str = None) -> dict:
        """Submit a form by selector or find submit button.
        
        Returns detailed information about the submission including:
        - Submitted URL (before submission)
        - Redirected URL (after submission)
        - Page title
        - Success/error messages
        - Response data if available
        """
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        try:
            # Store current URL and form data before submission
            url_before = self.page.url
            title_before = await self.page.title()
            
            # Try to capture form data before submission
            form_data = {}
            try:
                form_data = await self.page.evaluate("""
                    () => {
                        const form = document.querySelector('form');
                        if (!form) return {};
                        
                        const data = {};
                        const inputs = form.querySelectorAll('input, textarea, select');
                        inputs.forEach(input => {
                            if (input.type === 'checkbox' || input.type === 'radio') {
                                if (input.checked) {
                                    const name = input.name || input.id;
                                    if (name) {
                                        if (!data[name]) data[name] = [];
                                        data[name].push(input.value || input.checked);
                                    }
                                }
                            } else if (input.type !== 'submit' && input.type !== 'button' && input.type !== 'hidden') {
                                const name = input.name || input.id;
                                if (name && input.value) {
                                    data[name] = input.value;
                                }
                            }
                        });
                        return data;
                    }
                """)
            except:
                pass
            
            if selector:
                await self.page.wait_for_selector(selector, state="visible", timeout=5000)
                await self.page.click(selector)
            else:
                # Try to find submit button
                submit_selectors = [
                    "button[type='submit']",
                    "input[type='submit']",
                    "form button",
                    "[type='submit']"
                ]
                for sel in submit_selectors:
                    try:
                        await self.page.wait_for_selector(sel, state="visible", timeout=2000)
                        await self.page.click(sel)
                        break
                    except:
                        continue
                else:
                    return {"status": "error", "error": "No submit button found"}
            
            # Wait for navigation or result
            try:
                # Wait for navigation (if form causes redirect)
                await self.page.wait_for_load_state("networkidle", timeout=5000)
            except:
                # If no navigation, wait a bit for any dynamic content
                await self.page.wait_for_timeout(2000)
            
            url_after = self.page.url
            title_after = ""
            try:
                title_after = await self.page.title()
            except:
                pass
            
            # Detect what happened after submission
            result_info = await self._detect_form_result()
            
            # Try to extract response data from the page (for forms that show submitted data)
            response_data = {}
            try:
                # Check if page shows submitted form data (common in test forms like httpbin)
                page_text = await self.page.evaluate("() => document.body.innerText")
                if "form" in page_text.lower() or "submitted" in page_text.lower():
                    # Try to extract JSON if present
                    json_match = await self.page.evaluate("""
                        () => {
                            const scripts = Array.from(document.querySelectorAll('script'));
                            for (const script of scripts) {
                                if (script.textContent && script.textContent.includes('form')) {
                                    try {
                                        const jsonMatch = script.textContent.match(/\\{[\\s\\S]*form[\\s\\S]*\\}/);
                                        if (jsonMatch) {
                                            return JSON.parse(jsonMatch[0]);
                                        }
                                    } catch (e) {}
                                }
                            }
                            return null;
                        }
                    """)
                    if json_match:
                        response_data = json_match
                    else:
                        # Try to extract from pre tags (common in httpbin)
                        pre_content = await self.page.evaluate("""
                            () => {
                                const pre = document.querySelector('pre');
                                if (pre) {
                                    try {
                                        return JSON.parse(pre.textContent);
                                    } catch (e) {
                                        return { raw: pre.textContent };
                                    }
                                }
                                return null;
                            }
                        """)
                        if pre_content:
                            response_data = pre_content
            except:
                pass
            
            return {
                "status": "success",
                "submitted_url": url_before,
                "redirected_url": url_after,
                "url": url_after,  # Keep for backward compatibility
                "url_changed": url_after != url_before,
                "title": title_after,
                "title_before": title_before,
                "form_data": form_data,  # Data that was submitted
                "response_data": response_data,  # Response from server if available
                "result_info": result_info
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def _detect_form_result(self) -> dict:
        """Detect what happened after form submission (success, error, etc.)."""
        if not self.page:
            return {}
        
        try:
            result = await self.page.evaluate("""
                () => {
                    const info = {
                        hasSuccessMessage: false,
                        hasErrorMessage: false,
                        successSelectors: [],
                        errorSelectors: [],
                        messages: [],
                        urlChanged: false
                    };
                    
                    // Common success indicators
                    const successPatterns = [
                        /success/i,
                        /thank you/i,
                        /registered/i,
                        /signed up/i,
                        /created/i,
                        /welcome/i,
                        /confirmed/i,
                        /verified/i
                    ];
                    
                    // Common error indicators
                    const errorPatterns = [
                        /error/i,
                        /invalid/i,
                        /required/i,
                        /failed/i,
                        /try again/i,
                        /incorrect/i
                    ];
                    
                    // Check for success/error messages in common locations
                    const selectors = [
                        '.success', '.success-message', '.alert-success', '[class*="success"]',
                        '.error', '.error-message', '.alert-error', '[class*="error"]',
                        '.message', '.notification', '.alert', '.toast',
                        '[role="alert"]', '[role="status"]',
                        'div[class*="message"]', 'p[class*="message"]'
                    ];
                    
                    for (const sel of selectors) {
                        try {
                            const elements = document.querySelectorAll(sel);
                            elements.forEach(el => {
                                const text = el.textContent?.toLowerCase() || '';
                                const isVisible = el.offsetParent !== null && 
                                                 window.getComputedStyle(el).display !== 'none';
                                
                                if (isVisible && text.length > 0) {
                                    const isSuccess = successPatterns.some(pattern => pattern.test(text));
                                    const isError = errorPatterns.some(pattern => pattern.test(text));
                                    
                                    if (isSuccess) {
                                        info.hasSuccessMessage = true;
                                        info.successSelectors.push(sel);
                                        info.messages.push({
                                            type: 'success',
                                            selector: sel,
                                            text: el.textContent?.trim() || ''
                                        });
                                    } else if (isError) {
                                        info.hasErrorMessage = true;
                                        info.errorSelectors.push(sel);
                                        info.messages.push({
                                            type: 'error',
                                            selector: sel,
                                            text: el.textContent?.trim() || ''
                                        });
                                    }
                                }
                            });
                        } catch (e) {
                            continue;
                        }
                    }
                    
                    // Also check page title and body text for indicators
                    const bodyText = document.body.textContent?.toLowerCase() || '';
                    const titleText = document.title.toLowerCase();
                    
                    if (successPatterns.some(p => p.test(bodyText) || p.test(titleText))) {
                        info.hasSuccessMessage = true;
                    }
                    if (errorPatterns.some(p => p.test(bodyText) || p.test(titleText))) {
                        info.hasErrorMessage = true;
                    }
                    
                    return info;
                }
            """)
            
            return result
        except Exception as e:
            return {}

    async def extract(self, schema: dict, limit: int = None) -> dict:
        """Extract data from page using CSS selectors with site-specific fallbacks.
        
        Schema format: {"field_name": "css_selector"}
        Returns structured data with arrays for each field.
        """
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        # For YouTube, use specialized extraction
        if self.current_site == "youtube":
            return await YouTubeHandler.extract_video_urls(self.page, limit or 10)
        
        # For Google Search, use specialized extraction
        if self.current_site == "google":
            return await GoogleSearchHandler.extract_search_results(self.page, limit or 10)
        
        # Get site-specific selectors as fallback
        site_selectors = get_selectors_for_site(self.current_site)
        
        # First, try to diagnose the page structure - especially for Google Maps
        diagnostic = await self.page.evaluate(SiteExtractionHandler.get_diagnostic_js())
        
        
        try:
            # Use a smarter extraction strategy - extract from product containers
            result = await self.page.evaluate(
                SiteExtractionHandler.get_extraction_js(),
                {"schema": schema, "limit": limit or 0, "siteSelectors": site_selectors, "site": self.current_site}
            )
            
            # Transform to list of objects if multiple fields
            if result and len(result) > 0:
                import re  # Import at the top of the processing block
                field_names = list(result.keys())
                max_length = max(len(result[field]) for field in field_names) if result else 0
                
                # Create list of objects
                structured = []
                for i in range(max_length):
                    item = {}
                    for field in field_names:
                        value = result[field][i] if i < len(result[field]) else None
                        
                        # Clean and parse values
                        if field == 'price' and value:
                            # Extract numeric price (remove currency symbols, commas)
                            # Handle Indian format: ₹1,25,999 or 1,25,999 or ₹125999
                            price_clean = str(value).strip()
                            # Remove currency symbols and commas first
                            price_clean = re.sub(r'[₹$€£,\s]', '', price_clean)
                            # Extract only digits and decimal point
                            price_str = re.sub(r'[^\d.]', '', price_clean)
                            
                            if price_str:
                                try:
                                    item[field] = float(price_str)
                                except (ValueError, TypeError):
                                    # Fallback: try to extract first number
                                    numbers = re.findall(r'\d+\.?\d*', price_clean)
                                    if numbers:
                                        try:
                                            item[field] = float(numbers[0])
                                        except:
                                            item[field] = None
                                    else:
                                        item[field] = None
                            else:
                                item[field] = None
                        elif field == 'rating' and value:
                            # Extract numeric rating (handle "4.5", "4.5 out of 5", "4.5 Ratings", etc.)
                            # Try to extract just the number
                            rating_str = str(value).strip()
                            # Try to parse as float first
                            try:
                                rating_float = float(rating_str)
                                # Validate it's a reasonable rating (0-5)
                                if 0 <= rating_float <= 5:
                                    item[field] = rating_float
                                else:
                                    # If it's a large number, it might be the count, try to find the actual rating
                                    # Look for decimal pattern in the original value
                                    rating_match = re.search(r'(\d\.\d)', str(value))
                                    if rating_match:
                                        rating_float = float(rating_match.group(1))
                                        if 0 <= rating_float <= 5:
                                            item[field] = rating_float
                                        else:
                                            item[field] = None
                                    else:
                                        item[field] = None
                            except:
                                # If parsing fails, try regex to find decimal
                                rating_match = re.search(r'(\d\.\d)', rating_str)
                                if rating_match:
                                    try:
                                        rating_float = float(rating_match.group(1))
                                        if 0 <= rating_float <= 5:
                                            item[field] = rating_float
                                        else:
                                            item[field] = None
                                    except:
                                        item[field] = None
                                else:
                                    item[field] = None
                        elif field == 'link' or field == 'url':
                            # Ensure link is properly formatted
                            if value:
                                item[field] = str(value).strip()
                            else:
                                item[field] = None
                        elif field == 'name':
                            # Clean name
                            if value:
                                name = str(value).strip()
                                # Remove "Add to Compare" and similar prefixes
                                name = re.sub(r'^(Add to Compare|Compare|Add to Cart|Buy Now)\s*', '', name, flags=re.IGNORECASE)
                                item[field] = name.strip()
                            else:
                                item[field] = None
                        else:
                            item[field] = value
                    structured.append(item)
                
                return {
                    "status": "success",
                    "data": structured,
                    "count": len(structured)
                }
            
            # If no data found, include diagnostic info
            if not result or len(result) == 0 or (isinstance(result, dict) and all(not v or len(v) == 0 for v in result.values() if isinstance(v, list))):
                return {
                    "status": "success",
                    "data": [],
                    "count": 0,
                    "diagnostic": diagnostic,
                    "message": f"No data extracted. Found {diagnostic.get('selectorChecks', [{}])[0].get('count', 0)} product containers."
                }
            
            return {
                "status": "success",
                "data": [],
                "count": 0
            }
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            return {
                "status": "error",
                "error": str(e),
                "diagnostic": diagnostic if 'diagnostic' in locals() else None,
                "traceback": error_trace
            }

# Global instance
browser_agent = BrowserAgent()

