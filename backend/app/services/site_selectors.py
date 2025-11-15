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
            "div[data-id]",
            "._13oc-S"
        ],
        "product_name": [
            "._4rR01T",
            "div._4rR01T",
            "a._4rR01T",
            "._2WkVRV",
            "a.s1Q9rs",
            "a[title]",
            "div[class*='_4rR01T']",
            "span[class*='_4rR01T']",
            "[class*='product-name']",
            "h1",
            "h2",
            "h3"
        ],
        "product_price": [
            "._30jeq3",
            "div._30jeq3",
            "span._30jeq3",
            "._1_WHN1",
            "._25b18c",
            "div[class*='_30jeq3']",
            "span[class*='_30jeq3']",
            "[class*='price']",
            "div[class*='price']"
        ],
        "product_rating": [
            "._3LWZlK",
            "div._3LWZlK",
            "span._3LWZlK",
            "div[class*='_3LWZlK']",
            "[class*='rating']",
            "._2_R_DZ",
            "div._2_R_DZ span._2_R_DZ",
            "[aria-label*='star']"
        ],
        "product_link": [
            "a._1fQZEK",
            "a[href*='/p/']",
            "a.s1Q9rs",
            "a[href*='flipkart.com']",
            "div._1AtVbE a"
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
    },
    "google_maps": {
        "search_input": [
            "input#searchboxinput",
            "input[aria-label*='Search']",
            "input[placeholder*='Search']",
            "input[name='q']",
            "#searchboxinput"
        ],
        "search_button": [
            "button[data-value='Search']",
            "button[aria-label*='Search']",
            "button[jsaction*='search']"
        ],
        "result_container": [
            "[data-result-index]",
            ".section-result",
            "[class*='section-result']",
            "[class*='result-container']",
            "div[role='article']",
            "[data-result-index]"
        ],
        "result_name": [
            ".qBF1Pd",
            "h3",
            "[class*='qBF1Pd']",
            "[data-value='name']",
            "div[role='article'] h3",
            ".fontHeadlineSmall"
        ],
        "result_rating": [
            ".MW4etd",
            "[aria-label*='star']",
            "[class*='MW4etd']",
            "[data-value='rating']",
            ".fontBodyMedium"
        ],
        "result_location": [
            ".W4Efsd",
            "[class*='W4Efsd']",
            "[data-value='address']",
            ".fontBodyMedium",
            "[aria-label*='Address']"
        ],
        "result_link": [
            "a[href*='maps.google.com']",
            "a[data-value='url']",
            "[role='article'] a"
        ]
    },
    "youtube": {
        "search_input": [
            "input[name='search_query']",
            "#search",
            "input#search",
            "input[placeholder*='Search']",
            "input[aria-label*='Search']"
        ],
        "search_button": [
            "button#search-icon-legacy",
            "button[aria-label*='Search']",
            "button[type='submit']",
            "#search-icon-legacy"
        ],
        "result_container": [
            "#contents ytd-video-renderer",
            "#contents ytd-video-renderer, #contents ytd-playlist-renderer",
            "#contents > *",
            "ytd-video-renderer",
            "#dismissible"
        ],
        "result_title": [
            "#video-title",
            "a#video-title",
            "h3 a",
            "#video-title-link",
            "ytd-video-renderer #video-title"
        ],
        "result_link": [
            "a[href*='/watch']",
            "#video-title-link",
            "ytd-video-renderer a[href*='/watch']",
            "#contents a[href*='/watch']"
        ]
    },
    "swiggy": {
        "search_activation": [
            "div:has-text('Search for restaurant and food')",
            "a[href*='/search']",
            "[class*='search']"
        ],
        "search_input": [
            "input[placeholder*='Search for Dishes']",
            "input[placeholder*='Search for restaurant']",
            "input[type='text'][placeholder*='Search']",
            "input[class*='search']"
        ],
        "search_button": [
            "button[type='submit']",
            "button[aria-label*='Search']"
        ],
        "restaurant_container": [
            "div[data-testid='restaurant-card']",
            "[data-testid='restaurant-card']",
            "div[class*='restaurant-card']",
            "div[class*='RestaurantCard']",
            "a[class*='restaurant']"
        ],
        "restaurant_name": [
            "div[class*='restaurant-name']",
            "div[class*='RestaurantName']",
            "h3",
            "h2"
        ],
        "restaurant_rating": [
            "div[class*='rating']",
            "span[class*='rating']",
            "[aria-label*='star']",
            "div[class*='Rating']"
        ],
        "restaurant_cuisine": [
            "div[class*='cuisine']",
            "div[class*='Cuisine']",
            "span[class*='cuisine']"
        ],
        "restaurant_location": [
            "div[class*='location']",
            "div[class*='area']",
            "span[class*='location']"
        ],
        "restaurant_price": [
            "div[class*='price']",
            "span[class*='price']",
            "div[class*='cost']"
        ]
    }
}

def get_selectors_for_site(site_name: str = None) -> dict:
    """Get selector mappings for a specific site or generic fallback."""
    if site_name and site_name.lower() in SITE_SELECTORS:
        return SITE_SELECTORS[site_name.lower()]
    return SITE_SELECTORS["generic"]

def detect_site_from_url(url: str) -> str:
    """Detect which site from URL."""
    url_lower = url.lower()
    if "youtube" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    elif "flipkart" in url_lower:
        return "flipkart"
    elif "amazon" in url_lower:
        return "amazon"
    elif "myntra" in url_lower:
        return "myntra"
    elif "snapdeal" in url_lower:
        return "snapdeal"
    elif "google" in url_lower:
        if "maps" in url_lower:
            return "google_maps"
        return "google"
    elif "zomato" in url_lower:
        return "zomato"
    elif "swiggy" in url_lower:
        return "swiggy"
    elif "zomato" in url_lower or "swiggy" in url_lower:
        return "local"
    return "generic"

