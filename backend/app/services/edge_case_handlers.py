"""Edge case handlers for browser automation."""

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout, Error as PlaywrightError
from app.core.logger import logger
from typing import Optional, Any
import asyncio

class EdgeCaseHandler:
    """Handles common edge cases in browser automation."""
    
    @staticmethod
    async def handle_stale_element(page: Page, action_func, max_retries: int = 3):
        """
        Handle stale element references with retry logic.
        
        Element staleness occurs when the DOM changes after we've queried an element.
        This is common in SPAs with dynamic content.
        """
        for attempt in range(max_retries):
            try:
                return await action_func()
            except PlaywrightError as e:
                error_msg = str(e).lower()
                
                # Check if it's a staleness-related error
                if any(keyword in error_msg for keyword in [
                    'detached', 'stale', 'not attached', 'node is not connected'
                ]):
                    if attempt < max_retries - 1:
                        logger.warning(f"Stale element detected, retry {attempt + 1}/{max_retries}")
                        await asyncio.sleep(0.5 * (attempt + 1))  # Progressive backoff
                        # Re-query the element in the action_func
                        continue
                    else:
                        logger.error("Element remained stale after all retries")
                        raise
                else:
                    # Not a staleness error, re-raise
                    raise
    
    @staticmethod
    async def wait_for_network_idle(page: Page, timeout: int = 5000, max_wait: int = 30000):
        """
        Wait for network to become idle (no requests for a period).
        
        This is useful after navigation or interactions that trigger AJAX requests.
        Falls back gracefully if network never becomes idle.
        """
        try:
            await page.wait_for_load_state('networkidle', timeout=timeout)
            logger.debug("Network became idle")
            return {"status": "success", "waited": True}
        except PlaywrightTimeout:
            logger.debug(f"Network didn't become idle within {timeout}ms, continuing anyway")
            return {"status": "success", "waited": False, "note": "Network timeout, but continuing"}
        except Exception as e:
            logger.warning(f"Error waiting for network idle: {e}")
            return {"status": "success", "waited": False, "error": str(e)}
    
    @staticmethod
    async def handle_popup(page: Page):
        """
        Handle common popups that might interfere with automation.
        
        Includes: cookie banners, newsletters, ads, modals
        """
        popup_selectors = [
            # Cookie consent
            "button:has-text('Accept')",
            "button:has-text('I agree')",
            "[aria-label*='cookie' i] button",
            "#onetrust-accept-btn-handler",
            
            # Close buttons for modals
            "button[aria-label*='close' i]",
            "button.close",
            "[class*='modal'] button",
            ".popup-close",
            
            # Newsletter/ads
            "button:has-text('No thanks')",
            "button:has-text('Maybe later')",
            ".newsletter-close",
        ]
        
        for selector in popup_selectors:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    await element.click()
                    logger.debug(f"Closed popup with selector: {selector}")
                    await asyncio.sleep(0.5)  # Wait for animation
                    return True
            except Exception:
                continue
        
        return False
    
    @staticmethod
    async def safe_click(page: Page, selector: str, retries: int = 3) -> dict:
        """
        Safely click an element with edge case handling.
        
        Handles:
        - Element obscured by other elements
        - Element not clickable
        - Element staleness
        - Scroll into view if needed
        """
        for attempt in range(retries):
            try:
                element = await page.wait_for_selector(selector, state="visible", timeout=5000)
                
                if not element:
                    return {"status": "error", "error": f"Element not found: {selector}"}
                
                # Scroll into view if needed
                await element.scroll_into_view_if_needed()
                await asyncio.sleep(0.2)  # Let scroll settle
                
                # Try regular click first
                try:
                    await element.click(timeout=3000)
                    logger.debug(f"Clicked element: {selector}")
                    return {"status": "success", "selector": selector}
                
                except Exception as click_error:
                    # If regular click fails, try force click
                    logger.warning(f"Regular click failed, trying force click: {click_error}")
                    await element.click(force=True)
                    return {"status": "success", "selector": selector, "force": True}
            
            except PlaywrightTimeout:
                if attempt < retries - 1:
                    logger.warning(f"Click timeout, retry {attempt + 1}/{retries}")
                    await asyncio.sleep(1)
                    continue
                return {"status": "error", "error": f"Timeout waiting for element: {selector}"}
            
            except Exception as e:
                error_msg = str(e).lower()
                
                # Handle specific errors
                if "not attached" in error_msg or "detached" in error_msg:
                    if attempt < retries - 1:
                        logger.warning("Element became detached, retrying...")
                        await asyncio.sleep(0.5)
                        continue
                
                return {"status": "error", "error": f"Click failed: {str(e)}"}
        
        return {"status": "error", "error": "Click failed after all retries"}
    
    @staticmethod
    async def safe_type(page: Page, selector: str, text: str, clear_first: bool = True) -> dict:
        """
        Safely type text into an input field with edge case handling.
        
        Handles:
        - Input not editable
        - Input obscured
        - Autocomplete interference
        """
        try:
            element = await page.wait_for_selector(selector, state="visible", timeout=5000)
            
            if not element:
                return {"status": "error", "error": f"Element not found: {selector}"}
            
            # Scroll into view
            await element.scroll_into_view_if_needed()
            await asyncio.sleep(0.2)
            
            # Focus the element
            await element.focus()
            await asyncio.sleep(0.1)
            
            # Clear existing text if needed
            if clear_first:
                await element.fill('')
                await asyncio.sleep(0.1)
            
            # Type text
            await element.type(text, delay=50)  # Add delay between keystrokes for realism
            
            logger.debug(f"Typed into element: {selector}")
            return {"status": "success", "selector": selector, "text": text}
        
        except PlaywrightTimeout:
            return {"status": "error", "error": f"Timeout waiting for element: {selector}"}
        
        except Exception as e:
            return {"status": "error", "error": f"Type failed: {str(e)}"}
    
    @staticmethod
    async def wait_for_selector_with_fallbacks(
        page: Page,
        selectors: list,
        timeout: int = 5000,
        state: str = "visible"
    ) -> Optional[Any]:
        """
        Wait for any of multiple selectors to appear.
        
        Useful when exact selector is unknown or page structure varies.
        """
        for selector in selectors:
            try:
                element = await page.wait_for_selector(selector, state=state, timeout=timeout)
                if element:
                    logger.debug(f"Found element with selector: {selector}")
                    return element
            except PlaywrightTimeout:
                continue
            except Exception as e:
                logger.warning(f"Error with selector {selector}: {e}")
                continue
        
        return None
    
    @staticmethod
    async def check_for_blocking(page: Page) -> dict:
        """
        Check if page is blocked by CAPTCHA, login wall, or other barriers.
        
        Returns detection result with details.
        """
        url = page.url
        title = await page.title()
        
        # Check for CAPTCHA
        captcha_indicators = [
            "recaptcha", "captcha", "robot", "verify you're human",
            "unusual traffic", "security check"
        ]
        
        content = await page.content()
        content_lower = content.lower()
        title_lower = title.lower()
        
        for indicator in captcha_indicators:
            if indicator in content_lower or indicator in title_lower:
                return {
                    "blocked": True,
                    "type": "captcha",
                    "message": "CAPTCHA or security check detected"
                }
        
        # Check for login walls
        login_indicators = ["sign in", "log in", "login required", "authentication"]
        
        for indicator in login_indicators:
            if indicator in title_lower:
                return {
                    "blocked": True,
                    "type": "login_required",
                    "message": "Login required to access content"
                }
        
        # Check for geo-blocking
        if "not available" in content_lower and ("region" in content_lower or "country" in content_lower):
            return {
                "blocked": True,
                "type": "geo_blocked",
                "message": "Content not available in your region"
            }
        
        # Check for rate limiting
        rate_limit_indicators = ["too many requests", "rate limit", "slow down"]
        
        for indicator in rate_limit_indicators:
            if indicator in content_lower:
                return {
                    "blocked": True,
                    "type": "rate_limited",
                    "message": "Too many requests, rate limited"
                }
        
        return {"blocked": False}
    
    @staticmethod
    async def recover_from_network_error(page: Page, action_func, max_retries: int = 3):
        """
        Retry an action if network errors occur.
        
        Handles transient network failures gracefully.
        """
        for attempt in range(max_retries):
            try:
                return await action_func()
            
            except Exception as e:
                error_msg = str(e).lower()
                
                # Check if it's a network error
                if any(keyword in error_msg for keyword in [
                    'timeout', 'network', 'connection', 'net::err', 'failed to load'
                ]):
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff
                        logger.warning(
                            f"Network error detected, retry {attempt + 1}/{max_retries} after {wait_time}s: {e}"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error("Network error persisted after all retries")
                        raise
                else:
                    # Not a network error, re-raise
                    raise
        
        return {"status": "error", "error": "Action failed after all retries"}

