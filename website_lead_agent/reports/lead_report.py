"""
Lead Report Generator - Creates structured reports of businesses
that are potential web development clients.
"""

import csv
import json
from datetime import datetime
from pathlib import Path
from dataclasses import asdict

from website_lead_agent.scanner.google_maps_scanner import Business
from website_lead_agent.checker.website_checker import WebsiteReport


class LeadReportGenerator:
    """Generates reports of potential web development leads."""

    def __init__(self, output_dir: str = "reports_output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        businesses: list[Business],
        website_reports: dict[str, WebsiteReport],
        location: str,
    ) -> Path:
        """
        Generate a full lead report.

        Args:
            businesses: List of businesses found.
            website_reports: Map of website URL -> WebsiteReport.
            location: The search location used.

        Returns:
            Path to the generated CSV report.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = self.output_dir / f"leads_{timestamp}.csv"
        json_path = self.output_dir / f"leads_{timestamp}.json"

        leads = self._classify_leads(businesses, website_reports)

        self._write_csv(leads, csv_path)
        self._write_json(leads, json_path, location)

        return csv_path

    def _classify_leads(
        self,
        businesses: list[Business],
        website_reports: dict[str, WebsiteReport],
    ) -> list[dict]:
        """Classify each business as a lead with priority."""
        leads = []

        for biz in businesses:
            lead = {
                "name": biz.name,
                "address": biz.address,
                "phone": biz.phone or "N/A",
                "website": biz.website or "None",
                "rating": biz.rating,
                "total_ratings": biz.total_ratings,
                "business_type": ", ".join(biz.business_type[:3]),
                "priority": "Low",
                "reason": "",
                "website_score": None,
                "issues": "",
            }

            if not biz.has_website:
                lead["priority"] = "High"
                lead["reason"] = "No website found"
            elif biz.website and biz.website in website_reports:
                report = website_reports[biz.website]
                lead["website_score"] = report.score

                if not report.is_reachable:
                    lead["priority"] = "High"
                    lead["reason"] = "Website is unreachable"
                elif report.score < 40:
                    lead["priority"] = "High"
                    lead["reason"] = f"Very poor website (score: {report.score})"
                elif report.score < 60:
                    lead["priority"] = "Medium"
                    lead["reason"] = f"Website needs improvement (score: {report.score})"
                else:
                    lead["priority"] = "Low"
                    lead["reason"] = f"Decent website (score: {report.score})"

                lead["issues"] = "; ".join(report.issues)

            leads.append(lead)

        # Sort by priority: High > Medium > Low
        priority_order = {"High": 0, "Medium": 1, "Low": 2}
        leads.sort(key=lambda x: priority_order.get(x["priority"], 3))

        return leads

    def _write_csv(self, leads: list[dict], path: Path):
        """Write leads to a CSV file."""
        if not leads:
            return

        fieldnames = leads[0].keys()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(leads)

    def _write_json(self, leads: list[dict], path: Path, location: str):
        """Write leads to a JSON file with metadata."""
        output = {
            "generated_at": datetime.now().isoformat(),
            "location": location,
            "total_businesses": len(leads),
            "high_priority": sum(1 for l in leads if l["priority"] == "High"),
            "medium_priority": sum(1 for l in leads if l["priority"] == "Medium"),
            "low_priority": sum(1 for l in leads if l["priority"] == "Low"),
            "leads": leads,
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, default=str)

    def print_summary(
        self,
        businesses: list[Business],
        website_reports: dict[str, WebsiteReport],
    ):
        """Print a quick summary to the console."""
        no_website = [b for b in businesses if not b.has_website]
        poor_website = [
            url
            for url, report in website_reports.items()
            if report.needs_improvement
        ]

        print(f"\n{'=' * 60}")
        print(f"  LEAD GENERATION SUMMARY")
        print(f"{'=' * 60}")
        print(f"  Total businesses scanned:    {len(businesses)}")
        print(f"  Without any website:         {len(no_website)}")
        print(f"  With poor website (< 60):    {len(poor_website)}")
        print(f"  Total potential leads:        {len(no_website) + len(poor_website)}")
        print(f"{'=' * 60}\n")
