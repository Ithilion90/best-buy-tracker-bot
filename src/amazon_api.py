"""
Amazon Product Advertising API 5.0 Client

Legal alternative to web scraping. Provides official access to:
- Current product prices
- Product titles and descriptions
- Product images
- Availability status

Requires Amazon Associates account with PA API credentials.
Documentation: https://webservices.amazon.com/paapi5/documentation/
Library: https://github.com/sergioteula/python-amazon-paapi
"""

from typing import Optional, Tuple
from amazon_paapi import AmazonApi
from amazon_paapi.models import regions
from amazon_paapi.errors import AmazonException

try:
    from src.config import config
    from src.logger import logger
except ImportError:
    from config import config
    from logger import logger


class AmazonProductAPI:
    """
    Official Amazon Product Advertising API client.
    
    100% legal alternative to web scraping.
    Supports multiple Amazon marketplaces (regions).
    """
    
    # Map Amazon domains to python-amazon-paapi Country codes
    REGION_MAPPING = {
        'amazon.com': regions.US,
        'amazon.ca': regions.CA,
        'amazon.com.mx': regions.MX,
        'amazon.co.uk': regions.UK,
        'amazon.de': regions.DE,
        'amazon.fr': regions.FR,
        'amazon.it': regions.IT,
        'amazon.es': regions.ES,
        'amazon.co.jp': regions.JP,
        'amazon.in': regions.IN,
        'amazon.com.br': regions.BR,
        'amazon.com.au': regions.AU,
    }
    
    def __init__(self):
        """Initialize Amazon PA API client with credentials from config."""
        self.access_key = config.amazon_access_key
        self.secret_key = config.amazon_secret_key
        self.partner_tag = config.affiliate_tag
        
        # Cache API instances by region
        self._api_cache = {}
    
    def _get_api_instance(self, domain: str) -> AmazonApi:
        """
        Get or create API instance for specific Amazon domain.
        
        Args:
            domain: Amazon domain (e.g., 'amazon.it', 'amazon.com')
        
        Returns:
            Configured AmazonApi instance
        
        Raises:
            ValueError: If domain not supported
        """
        if domain not in self.REGION_MAPPING:
            logger.warning("Unsupported domain, defaulting to amazon.com", domain=domain)
            domain = 'amazon.com'
        
        if domain in self._api_cache:
            return self._api_cache[domain]
        
        country = self.REGION_MAPPING[domain]
        
        api = AmazonApi(
            key=self.access_key,
            secret=self.secret_key,
            tag=self.partner_tag,
            country=country,
            throttling=1.0  # 1 request per second (free tier limit)
        )
        
        self._api_cache[domain] = api
        return api
    
    def get_product_data(
        self, 
        asin: str, 
        domain: str = 'amazon.com'
    ) -> Tuple[Optional[str], Optional[float], Optional[str], Optional[str], Optional[str]]:
        """
        Fetch current product data from Amazon PA API.
        
        LEGAL method - uses official Amazon API with proper authorization.
        
        Args:
            asin: Product ASIN
            domain: Amazon domain (e.g., 'amazon.it')
        
        Returns:
            Tuple of (title, price, currency, image_url, availability)
            Returns (None, None, None, None, None) on error
        
        Example:
            >>> api = AmazonProductAPI()
            >>> title, price, currency, image, avail = api.get_product_data('B07RW6Z692', 'amazon.it')
            >>> print(f"{title}: €{price} - {avail}")
        """
        try:
            api = self._get_api_instance(domain)
            
            # Get item with required resources
            product = api.get_items(asin)[0]
            
            if not product:
                logger.warning("No product found in PA API response", asin=asin, domain=domain)
                return None, None, None, None, None
            
            # Extract title
            title = product.item_info.title.display_value if product.item_info and product.item_info.title else None
            
            # Extract price and currency
            price = None
            currency = None
            if product.offers and product.offers.listings and len(product.offers.listings) > 0:
                listing = product.offers.listings[0]
                if listing.price:
                    price = listing.price.amount
                    currency = listing.price.currency
            
            # Extract image URL
            image_url = None
            if product.images and product.images.primary and product.images.primary.large:
                image_url = product.images.primary.large.url
            
            # Extract availability
            availability = "unknown"
            if product.offers and product.offers.listings and len(product.offers.listings) > 0:
                listing = product.offers.listings[0]
                if listing.availability:
                    if listing.availability.type:
                        availability = listing.availability.type.lower()
                    elif listing.availability.message:
                        # Parse availability message
                        msg = listing.availability.message.lower()
                        if 'in stock' in msg or 'available' in msg:
                            availability = 'available'
                        elif 'out of stock' in msg or 'unavailable' in msg:
                            availability = 'unavailable'
            
            logger.info(
                "PA API product data fetched",
                asin=asin,
                domain=domain,
                title=title[:50] if title else None,
                price=price,
                currency=currency,
                availability=availability
            )
            
            return title, price, currency, image_url, availability
            
        except AmazonException as e:
            logger.error(
                "Amazon PA API error",
                asin=asin,
                domain=domain,
                error=str(e)
            )
            return None, None, None, None, None
        
        except Exception as e:
            logger.error(
                "Unexpected error in PA API",
                asin=asin,
                domain=domain,
                error=str(e),
                error_type=type(e).__name__
            )
            return None, None, None, None, None


# Singleton instance
_amazon_api_instance = None


def get_amazon_api() -> AmazonProductAPI:
    """Get singleton Amazon PA API instance."""
    global _amazon_api_instance
    if _amazon_api_instance is None:
        _amazon_api_instance = AmazonProductAPI()
    return _amazon_api_instance


# Convenience function matching old scraper interface
def fetch_product_data_legal(
    asin: str,
    domain: str = 'amazon.com'
) -> Tuple[Optional[str], Optional[float], Optional[str], Optional[str], Optional[str]]:
    """
    Legal product data fetch using official Amazon PA API.
    
    Drop-in replacement for old fetch_price_title_image_and_availability().
    
    Args:
        asin: Product ASIN
        domain: Amazon domain
    
    Returns:
        (title, price, currency, image_url, availability)
    """
    api = get_amazon_api()
    return api.get_product_data(asin, domain)

    
    def __init__(self):
        """Initialize Amazon PA API client with credentials from config."""
        self.access_key = config.amazon_access_key
        self.secret_key = config.amazon_secret_key
        self.partner_tag = config.affiliate_tag
        
        # Cache API instances by region
        self._api_cache = {}
    
    def _get_api_instance(self, domain: str) -> DefaultApi:
        """
        Get or create API instance for specific Amazon domain.
        
        Args:
            domain: Amazon domain (e.g., 'amazon.it', 'amazon.com')
        
        Returns:
            Configured DefaultApi instance
        
        Raises:
            ValueError: If domain not supported
        """
        if domain not in self.REGION_MAPPING:
            logger.warning("Unsupported domain, defaulting to amazon.com", domain=domain)
            domain = 'amazon.com'
        
        if domain in self._api_cache:
            return self._api_cache[domain]
        
        region, host = self.REGION_MAPPING[domain]
        
        api = DefaultApi(
            access_key=self.access_key,
            secret_key=self.secret_key,
            host=host,
            region=region
        )
        
        self._api_cache[domain] = api
        return api
    
    def get_product_data(
        self, 
        asin: str, 
        domain: str = 'amazon.com'
    ) -> Tuple[Optional[str], Optional[float], Optional[str], Optional[str], Optional[str]]:
        """
        Fetch current product data from Amazon PA API.
        
        LEGAL method - uses official Amazon API with proper authorization.
        
        Args:
            asin: Product ASIN
            domain: Amazon domain (e.g., 'amazon.it')
        
        Returns:
            Tuple of (title, price, currency, image_url, availability)
            Returns (None, None, None, None, None) on error
        
        Example:
            >>> api = AmazonProductAPI()
            >>> title, price, currency, image, avail = api.get_product_data('B07RW6Z692', 'amazon.it')
            >>> print(f"{title}: €{price} - {avail}")
        """
        try:
            api = self._get_api_instance(domain)
            
            # Configure resources to fetch
            resources = [
                GetItemsResource.OFFERS_LISTINGS_PRICE,
                GetItemsResource.ITEMINFO_TITLE,
                GetItemsResource.IMAGES_PRIMARY_LARGE,
                GetItemsResource.OFFERS_LISTINGS_AVAILABILITY_MESSAGE,
                GetItemsResource.OFFERS_LISTINGS_AVAILABILITY_TYPE,
            ]
            
            # Create request
            request = GetItemsRequest(
                partner_tag=self.partner_tag,
                partner_type=PartnerType.ASSOCIATES,
                marketplace=domain,
                item_ids=[asin],
                resources=resources
            )
            
            # Execute API call
            response = api.get_items(request)
            
            # Check if we got valid response
            if not response.items_result:
                logger.warning("No items_result in PA API response", asin=asin, domain=domain)
                return None, None, None, None, None
            
            if not response.items_result.items:
                logger.warning("No items in PA API response", asin=asin, domain=domain)
                return None, None, None, None, None
            
            item = response.items_result.items[0]
            
            # Extract title
            title = None
            if item.item_info and item.item_info.title:
                title = item.item_info.title.display_value
            
            # Extract price and currency
            price = None
            currency = None
            if item.offers and item.offers.listings and len(item.offers.listings) > 0:
                listing = item.offers.listings[0]
                if listing.price:
                    price = listing.price.amount
                    currency = listing.price.currency
            
            # Extract image URL
            image_url = None
            if item.images and item.images.primary and item.images.primary.large:
                image_url = item.images.primary.large.url
            
            # Extract availability
            availability = "unknown"
            if item.offers and item.offers.listings and len(item.offers.listings) > 0:
                listing = item.offers.listings[0]
                if listing.availability:
                    if listing.availability.type:
                        availability = listing.availability.type.lower()
                    elif listing.availability.message:
                        # Parse availability message
                        msg = listing.availability.message.lower()
                        if 'in stock' in msg or 'available' in msg:
                            availability = 'available'
                        elif 'out of stock' in msg or 'unavailable' in msg:
                            availability = 'unavailable'
            
            logger.info(
                "PA API product data fetched",
                asin=asin,
                domain=domain,
                title=title[:50] if title else None,
                price=price,
                currency=currency,
                availability=availability
            )
            
            return title, price, currency, image_url, availability
            
        except ApiException as e:
            logger.error(
                "Amazon PA API error",
                asin=asin,
                domain=domain,
                error=str(e),
                status=e.status if hasattr(e, 'status') else None
            )
            return None, None, None, None, None
        
        except Exception as e:
            logger.error(
                "Unexpected error in PA API",
                asin=asin,
                domain=domain,
                error=str(e),
                error_type=type(e).__name__
            )
            return None, None, None, None, None
    
    def get_multiple_products(
        self,
        asins: list[str],
        domain: str = 'amazon.com'
    ) -> dict[str, Tuple[Optional[str], Optional[float], Optional[str], Optional[str], Optional[str]]]:
        """
        Fetch multiple products in a single API call (more efficient).
        
        Args:
            asins: List of ASINs (max 10 per request per API limits)
            domain: Amazon domain
        
        Returns:
            Dict mapping ASIN -> (title, price, currency, image_url, availability)
        
        Note:
            PA API allows max 10 ASINs per request.
            For more, split into multiple calls.
        """
        # PA API limit: max 10 items per request
        if len(asins) > 10:
            logger.warning("Too many ASINs for single request, using first 10", count=len(asins))
            asins = asins[:10]
        
        try:
            api = self._get_api_instance(domain)
            
            resources = [
                GetItemsResource.OFFERS_LISTINGS_PRICE,
                GetItemsResource.ITEMINFO_TITLE,
                GetItemsResource.IMAGES_PRIMARY_LARGE,
                GetItemsResource.OFFERS_LISTINGS_AVAILABILITY_MESSAGE,
                GetItemsResource.OFFERS_LISTINGS_AVAILABILITY_TYPE,
            ]
            
            request = GetItemsRequest(
                partner_tag=self.partner_tag,
                partner_type=PartnerType.ASSOCIATES,
                marketplace=domain,
                item_ids=asins,
                resources=resources
            )
            
            response = api.get_items(request)
            
            results = {}
            
            if response.items_result and response.items_result.items:
                for item in response.items_result.items:
                    asin = item.asin
                    
                    # Extract same data as single product
                    title = item.item_info.title.display_value if item.item_info and item.item_info.title else None
                    
                    price = None
                    currency = None
                    if item.offers and item.offers.listings and len(item.offers.listings) > 0:
                        listing = item.offers.listings[0]
                        if listing.price:
                            price = listing.price.amount
                            currency = listing.price.currency
                    
                    image_url = None
                    if item.images and item.images.primary and item.images.primary.large:
                        image_url = item.images.primary.large.url
                    
                    availability = "unknown"
                    if item.offers and item.offers.listings and len(item.offers.listings) > 0:
                        listing = item.offers.listings[0]
                        if listing.availability and listing.availability.type:
                            availability = listing.availability.type.lower()
                    
                    results[asin] = (title, price, currency, image_url, availability)
            
            logger.info("PA API batch fetch completed", domain=domain, requested=len(asins), fetched=len(results))
            return results
            
        except ApiException as e:
            logger.error("Amazon PA API batch error", domain=domain, asins=asins, error=str(e))
            return {}
        
        except Exception as e:
            logger.error("Unexpected error in PA API batch", domain=domain, error=str(e))
            return {}


# Singleton instance
_amazon_api_instance = None


def get_amazon_api() -> AmazonProductAPI:
    """Get singleton Amazon PA API instance."""
    global _amazon_api_instance
    if _amazon_api_instance is None:
        _amazon_api_instance = AmazonProductAPI()
    return _amazon_api_instance


# Convenience function matching old scraper interface
async def fetch_product_data_legal(
    asin: str,
    domain: str = 'amazon.com'
) -> Tuple[Optional[str], Optional[float], Optional[str], Optional[str], Optional[str]]:
    """
    Legal product data fetch using official Amazon PA API.
    
    Drop-in replacement for old fetch_price_title_image_and_availability().
    
    Args:
        asin: Product ASIN
        domain: Amazon domain
    
    Returns:
        (title, price, currency, image_url, availability)
    """
    api = get_amazon_api()
    return api.get_product_data(asin, domain)
