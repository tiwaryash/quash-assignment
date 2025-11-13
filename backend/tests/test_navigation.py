"""
End-to-end tests for browser navigation functionality.

These tests verify the core browser automation capabilities including:
- Navigation to URLs
- Element waiting and detection
- Basic interaction patterns
- Error handling
"""

import pytest
import asyncio
from app.services.browser_agent import BrowserAgent

@pytest.mark.asyncio
async def test_navigate_to_valid_url():
    """Test navigation to a valid URL."""
    agent = BrowserAgent()
    
    try:
        await agent.start()
        result = await agent.navigate("https://example.com")
        
        assert result["status"] == "success", f"Navigation failed: {result.get('error')}"
        assert agent.page is not None, "Page object should be initialized"
        assert "example.com" in agent.page.url.lower(), "Should navigate to correct URL"
        
    finally:
        await agent.close()

@pytest.mark.asyncio
async def test_navigate_to_invalid_url():
    """Test navigation to an invalid URL with proper error handling."""
    agent = BrowserAgent()
    
    try:
        await agent.start()
        result = await agent.navigate("https://this-domain-definitely-does-not-exist-12345.com")
        
        # Should return error status, not crash
        assert result["status"] in ["error", "blocked"], "Should handle invalid URLs gracefully"
        assert "error" in result or "message" in result, "Should provide error details"
        
    finally:
        await agent.close()

@pytest.mark.asyncio
async def test_navigate_without_protocol():
    """Test navigation without protocol (should add https://)."""
    agent = BrowserAgent()
    
    try:
        await agent.start()
        result = await agent.navigate("example.com")
        
        assert result["status"] == "success", "Should handle URLs without protocol"
        assert agent.page is not None
        
    finally:
        await agent.close()

@pytest.mark.asyncio
async def test_wait_for_element():
    """Test waiting for element to appear."""
    agent = BrowserAgent()
    
    try:
        await agent.start()
        await agent.navigate("https://example.com")
        
        # Wait for a selector that exists
        result = await agent.wait_for("h1", timeout=5000)
        
        assert result["status"] == "success", "Should find existing element"
        
    finally:
        await agent.close()

@pytest.mark.asyncio
async def test_wait_for_nonexistent_element():
    """Test waiting for element that doesn't exist (should timeout)."""
    agent = BrowserAgent()
    
    try:
        await agent.start()
        await agent.navigate("https://example.com")
        
        # Wait for a selector that doesn't exist
        result = await agent.wait_for(".this-class-does-not-exist-12345", timeout=2000)
        
        assert result["status"] == "error", "Should timeout for non-existent element"
        
    finally:
        await agent.close()

@pytest.mark.asyncio
async def test_extract_basic_content():
    """Test extracting content from a page."""
    agent = BrowserAgent()
    
    try:
        await agent.start()
        await agent.navigate("https://example.com")
        
        # Extract title
        result = await agent.extract({
            "title": "h1"
        }, limit=1)
        
        assert result["status"] == "success", "Should extract content successfully"
        assert len(result["data"]) > 0, "Should find at least one result"
        assert "title" in result["data"][0], "Should extract title field"
        
    finally:
        await agent.close()

@pytest.mark.asyncio
async def test_site_detection():
    """Test site detection from URL."""
    agent = BrowserAgent()
    
    try:
        await agent.start()
        
        # Test various site detections
        await agent.navigate("https://www.flipkart.com")
        assert agent.current_site == "flipkart", "Should detect Flipkart"
        
        await agent.navigate("https://www.amazon.in")
        assert agent.current_site == "amazon", "Should detect Amazon"
        
        await agent.navigate("https://www.google.com/maps")
        assert agent.current_site == "google_maps", "Should detect Google Maps"
        
    finally:
        await agent.close()

@pytest.mark.asyncio
async def test_browser_restart():
    """Test browser can be restarted after closing."""
    agent = BrowserAgent()
    
    try:
        # Start, close, and restart
        await agent.start()
        await agent.navigate("https://example.com")
        await agent.close()
        
        # Should be able to restart
        await agent.start()
        result = await agent.navigate("https://example.com")
        
        assert result["status"] == "success", "Should restart browser successfully"
        
    finally:
        await agent.close()

@pytest.mark.asyncio
async def test_concurrent_operations():
    """Test that agent handles operations sequentially."""
    agent = BrowserAgent()
    
    try:
        await agent.start()
        
        # Navigate and immediately try to wait for element
        await agent.navigate("https://example.com")
        result = await agent.wait_for("h1", timeout=5000)
        
        assert result["status"] == "success", "Should handle sequential operations"
        
    finally:
        await agent.close()

if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])

