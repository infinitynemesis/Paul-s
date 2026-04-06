"""
Website Quality Checker - Evaluates existing websites for quality issues
that suggest they need improvement or a redesign.
"""

import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass
class WebsiteReport:
    """Quality report for a single website."""
    url: str
    is_reachable: bool = False
    load_time_seconds: float = 0.0
    has_ssl: bool = False
    is_mobile_responsive: bool = False
    has_meta_description: bool = False
    has_proper_title: bool = False
    has_favicon: bool = False
    has_social_meta: bool = False
    page_size_kb: float = 0.0
    image_count: int = 0
    broken_links: int = 0
    uses_modern_tech: bool = False
    issues: list[str] = field(default_factory=list)
    score: int = 0  # 0-100, higher is better

    @property
    def needs_improvement(self) -> bool:
        return self.score < 60


class WebsiteChecker:
    """Checks website quality and identifies improvement opportunities."""

    TIMEOUT = 15
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; WebsiteLeadAgent/1.0; "
            "+https://github.com/infinitynemesis/paul-s)"
        )
    }

    def check(self, url: str) -> WebsiteReport:
        """
        Run a full quality check on a website.

        Args:
            url: The website URL to check.

        Returns:
            WebsiteReport with findings and a quality score.
        """
        report = WebsiteReport(url=url)

        # Normalize URL
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        report.has_ssl = url.startswith("https://")

        # Try to fetch the page
        try:
            response = requests.get(
                url,
                timeout=self.TIMEOUT,
                headers=self.HEADERS,
                allow_redirects=True,
            )
            report.is_reachable = response.status_code == 200
            report.load_time_seconds = response.elapsed.total_seconds()
            report.page_size_kb = len(response.content) / 1024

            if report.is_reachable:
                soup = BeautifulSoup(response.text, "lxml")
                self._check_html_quality(soup, report)
                self._check_mobile_responsiveness(soup, report)
                self._check_modern_tech(soup, response.text, report)

        except requests.exceptions.SSLError:
            report.is_reachable = False
            report.has_ssl = False
            report.issues.append("SSL certificate error")
        except requests.exceptions.Timeout:
            report.is_reachable = False
            report.issues.append("Website timed out (>15s)")
        except requests.exceptions.ConnectionError:
            report.is_reachable = False
            report.issues.append("Could not connect to website")
        except Exception as e:
            report.is_reachable = False
            report.issues.append(f"Unexpected error: {e}")

        report.score = self._calculate_score(report)
        return report

    def _check_html_quality(self, soup: BeautifulSoup, report: WebsiteReport):
        """Check basic HTML quality signals."""
        # Title tag
        title = soup.find("title")
        report.has_proper_title = bool(
            title and title.string and len(title.string.strip()) > 5
        )
        if not report.has_proper_title:
            report.issues.append("Missing or poor page title")

        # Meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        report.has_meta_description = bool(
            meta_desc and meta_desc.get("content", "").strip()
        )
        if not report.has_meta_description:
            report.issues.append("Missing meta description (bad for SEO)")

        # Favicon
        favicon = soup.find("link", rel=lambda x: x and "icon" in x)
        report.has_favicon = bool(favicon)
        if not report.has_favicon:
            report.issues.append("Missing favicon")

        # Open Graph / social meta
        og_tags = soup.find_all("meta", property=lambda x: x and x.startswith("og:"))
        report.has_social_meta = len(og_tags) >= 2
        if not report.has_social_meta:
            report.issues.append("Missing Open Graph meta tags")

        # Count images
        report.image_count = len(soup.find_all("img"))

    def _check_mobile_responsiveness(
        self, soup: BeautifulSoup, report: WebsiteReport
    ):
        """Check if the site appears mobile-responsive."""
        viewport = soup.find("meta", attrs={"name": "viewport"})
        has_viewport = bool(viewport)

        # Check for responsive CSS indicators
        styles = soup.find_all("link", rel="stylesheet")
        style_tags = soup.find_all("style")
        all_css = " ".join(str(s) for s in style_tags)
        has_media_queries = "@media" in all_css

        report.is_mobile_responsive = has_viewport or has_media_queries
        if not report.is_mobile_responsive:
            report.issues.append("Not mobile-responsive (no viewport meta tag)")

    def _check_modern_tech(
        self, soup: BeautifulSoup, html: str, report: WebsiteReport
    ):
        """Check if the website uses modern web technologies."""
        modern_indicators = [
            "react",
            "vue",
            "angular",
            "next",
            "nuxt",
            "tailwind",
            "bootstrap",
            "webpack",
            "vite",
        ]

        html_lower = html.lower()
        report.uses_modern_tech = any(
            indicator in html_lower for indicator in modern_indicators
        )

        # Check for outdated indicators
        outdated_indicators = [
            ("flash", "Uses Flash (deprecated)"),
            ("frameset", "Uses HTML framesets (very outdated)"),
            ("marquee", "Uses marquee tag (outdated)"),
            ("table-layout", "May use table-based layout (outdated)"),
        ]

        for indicator, issue in outdated_indicators:
            if indicator in html_lower:
                report.issues.append(issue)

        # Check page load speed
        if report.load_time_seconds > 5:
            report.issues.append(
                f"Slow page load ({report.load_time_seconds:.1f}s)"
            )
        elif report.load_time_seconds > 3:
            report.issues.append(
                f"Moderate page load time ({report.load_time_seconds:.1f}s)"
            )

    def _calculate_score(self, report: WebsiteReport) -> int:
        """Calculate an overall quality score (0-100)."""
        if not report.is_reachable:
            return 0

        score = 100
        deductions = {
            "has_ssl": 20,
            "is_mobile_responsive": 20,
            "has_meta_description": 10,
            "has_proper_title": 10,
            "has_favicon": 5,
            "has_social_meta": 5,
            "uses_modern_tech": 10,
        }

        for attr, penalty in deductions.items():
            if not getattr(report, attr, False):
                score -= penalty

        # Speed penalty
        if report.load_time_seconds > 5:
            score -= 15
        elif report.load_time_seconds > 3:
            score -= 10

        return max(0, score)
