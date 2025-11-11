"""Site-specific selector mappings for different e-commerce platforms."""

SITE_SELECTORS = {
    "flipkart": {
        "search_input": [
            "input[name='q']",
            "._3704LK",
            "input[placeholder*='Search']",
            "input[type='text'][placeholder*='Search']"
        ],
        "search_button": [
            "button[type='submit']",
            "._2KpZ6l",
            ".L0Z3Pu",
            "button._2KpZ6l._2doB4z"
        ],
        "product_container": [
            "[data-id]",
            "._1AtVbE",
            "._2kHMtA",
            "div[data-id]"
        ],
        "product_name": [
            "._4rR01T",
            "._2WkVRV",
            "a.s1Q9rs",
            "[class*='product-name']"
        ],
        "product_price": [
            "._30jeq3",
            "._1_WHN1",
            "[class*='price']",
            "._25b18c"
        ],
        "product_rating": [
            "._3LWZlK",
            "[class*='rating']",
            "._2_R_DZ"
        ],
        "product_link": [
            "a._1fQZEK",
            "a[href*='/p/']",
            "a.s1Q9rs",
            "a[href*='flipkart.com']"
        ]
    },
    "amazon": {
        "search_input": [
            "input[id='twotabsearchtextbox']",
            "#nav-search-input",
            "input[name='field-keywords']",
            "input[type='text'][placeholder*='Search']"
        ],
        "search_button": [
            "input[type='submit'][value='Go']",
            "#nav-search-submit-button",
            "input.nav-input[type='submit']"
        ],
        "product_container": [
            "[data-component-type='s-search-result']",
            ".s-result-item",
            "[data-asin]"
        ],
        "product_name": [
            "h2.a-size-mini a span",
            ".a-text-normal",
            "h2 a span",
            "[data-cy='title-recipe']"
        ],
        "product_price": [
            ".a-price-whole",
            ".a-price .a-offscreen",
            ".a-price",
            "[data-a-color='price']"
        ],
        "product_rating": [
            ".a-icon-alt",
            "[aria-label*='stars']",
            ".a-icon-star",
            "[data-hook='rating']"
        ],
        "product_link": [
            "a.a-link-normal[href*='/dp/']",
            "h2 a",
            "a[href*='amazon']"
        ]
    },
    "generic": {
        "search_input": [
            "input[name='q']",
            "input[type='search']",
            "input[placeholder*='Search']",
            "[role='searchbox']",
            "#search",
            ".search-input"
        ],
        "search_button": [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Search')",
            "[aria-label*='Search']"
        ],
        "product_container": [
            "[data-id]",
            ".product",
            ".item",
            "[class*='product']",
            "[class*='item']"
        ],
        "product_name": [
            ".product-name",
            "h2",
            "h3",
            "[class*='title']",
            "[class*='name']"
        ],
        "product_price": [
            ".price",
            "[class*='price']",
            "[data-price]",
            "[class*='cost']"
        ],
        "product_rating": [
            ".rating",
            "[class*='rating']",
            "[aria-label*='star']",
            "[class*='star']"
        ],
        "product_link": [
            "a[href*='/p/']",
            "a[href*='/product']",
            "a.product-link",
            "a[href*='http']"
        ]
    }
}

def get_selectors_for_site(site_name: str = None) -> dict:
    """Get selector mappings for a specific site or generic fallback."""
    if site_name and site_name.lower() in SITE_SELECTORS:
        return SITE_SELECTORS[site_name.lower()]
    return SITE_SELECTORS["generic"]

def detect_site_from_url(url: str) -> str:
    """Detect which e-commerce site from URL."""
    url_lower = url.lower()
    if "flipkart" in url_lower:
        return "flipkart"
    elif "amazon" in url_lower:
        return "amazon"
    elif "myntra" in url_lower:
        return "myntra"
    elif "snapdeal" in url_lower:
        return "snapdeal"
    return "generic"

