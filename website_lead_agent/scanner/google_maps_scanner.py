"""
Google Maps Scanner - Finds businesses in a given area using the Google Places API
and identifies which ones lack a website or have a potentially outdated one.
"""

import googlemaps
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Business:
    """Represents a business found on Google Maps."""
    name: str
    place_id: str
    address: str
    phone: Optional[str] = None
    website: Optional[str] = None
    rating: Optional[float] = None
    total_ratings: int = 0
    business_type: list[str] = field(default_factory=list)
    lat: float = 0.0
    lng: float = 0.0
    has_website: bool = False
    needs_improvement: bool = False


class GoogleMapsScanner:
    """Scans Google Maps for businesses in a given area."""

    # Business types likely to need websites
    TARGET_TYPES = [
        "restaurant",
        "store",
        "beauty_salon",
        "hair_care",
        "gym",
        "dentist",
        "doctor",
        "lawyer",
        "accounting",
        "plumber",
        "electrician",
        "car_repair",
        "real_estate_agency",
        "bakery",
        "cafe",
        "bar",
        "clothing_store",
        "florist",
        "pet_store",
        "veterinary_care",
        "pharmacy",
        "laundry",
        "locksmith",
        "moving_company",
        "painter",
        "roofing_contractor",
    ]

    def __init__(self, api_key: str):
        self.client = googlemaps.Client(key=api_key)

    def search_area(
        self,
        location: str,
        radius_meters: int = 5000,
        business_types: list[str] | None = None,
    ) -> list[Business]:
        """
        Search for businesses in a given area.

        Args:
            location: Address or "lat,lng" string for the search center.
            radius_meters: Search radius in meters (max 50000).
            business_types: Specific business types to search for.
                            Defaults to TARGET_TYPES.

        Returns:
            List of Business objects found in the area.
        """
        types_to_search = business_types or self.TARGET_TYPES
        geocode = self._geocode_location(location)
        if not geocode:
            return []

        all_businesses: dict[str, Business] = {}

        for btype in types_to_search:
            results = self._nearby_search(geocode, radius_meters, btype)
            for place in results:
                pid = place.get("place_id", "")
                if pid and pid not in all_businesses:
                    biz = self._parse_place(place)
                    all_businesses[pid] = biz

        return list(all_businesses.values())

    def get_details(self, business: Business) -> Business:
        """Fetch full details for a business (website, phone, etc.)."""
        try:
            result = self.client.place(
                business.place_id,
                fields=[
                    "website",
                    "formatted_phone_number",
                    "rating",
                    "user_ratings_total",
                    "type",
                ],
            )
            details = result.get("result", {})

            business.website = details.get("website")
            business.phone = details.get("formatted_phone_number")
            business.rating = details.get("rating")
            business.total_ratings = details.get("user_ratings_total", 0)
            business.business_type = details.get("types", [])
            business.has_website = bool(business.website)

            return business
        except Exception as e:
            print(f"Error fetching details for {business.name}: {e}")
            return business

    def enrich_businesses(self, businesses: list[Business]) -> list[Business]:
        """Fetch full details for a list of businesses."""
        enriched = []
        for biz in businesses:
            enriched.append(self.get_details(biz))
        return enriched

    def filter_no_website(self, businesses: list[Business]) -> list[Business]:
        """Return businesses that have no website."""
        return [b for b in businesses if not b.has_website]

    def _geocode_location(self, location: str) -> tuple[float, float] | None:
        """Convert an address or location string to lat/lng."""
        # Check if already lat,lng format
        if "," in location:
            parts = location.split(",")
            try:
                return (float(parts[0].strip()), float(parts[1].strip()))
            except ValueError:
                pass

        try:
            results = self.client.geocode(location)
            if results:
                loc = results[0]["geometry"]["location"]
                return (loc["lat"], loc["lng"])
        except Exception as e:
            print(f"Geocoding error for '{location}': {e}")
        return None

    def _nearby_search(
        self,
        location: tuple[float, float],
        radius: int,
        place_type: str,
    ) -> list[dict]:
        """Execute a nearby search for a specific business type."""
        all_results = []
        try:
            response = self.client.places_nearby(
                location=location,
                radius=radius,
                type=place_type,
            )
            all_results.extend(response.get("results", []))

            # Follow pagination (up to 3 pages max from Google)
            while "next_page_token" in response:
                import time
                time.sleep(2)  # Google requires a short delay between pages
                response = self.client.places_nearby(
                    page_token=response["next_page_token"]
                )
                all_results.extend(response.get("results", []))

        except Exception as e:
            print(f"Search error for type '{place_type}': {e}")

        return all_results

    def _parse_place(self, place: dict) -> Business:
        """Parse a Google Places API result into a Business object."""
        loc = place.get("geometry", {}).get("location", {})
        return Business(
            name=place.get("name", "Unknown"),
            place_id=place.get("place_id", ""),
            address=place.get("vicinity", ""),
            rating=place.get("rating"),
            total_ratings=place.get("user_ratings_total", 0),
            business_type=place.get("types", []),
            lat=loc.get("lat", 0.0),
            lng=loc.get("lng", 0.0),
        )
