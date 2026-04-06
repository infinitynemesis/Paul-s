#!/usr/bin/env python3
"""
Website Lead Agent - CLI entry point.

Scans Google Maps for businesses that either:
1. Don't have a website at all
2. Have a website that needs improvement

Usage:
    python -m website_lead_agent.main --location "Lagos, Nigeria" --radius 5000
    python -m website_lead_agent.main --location "40.7128,-74.0060" --types restaurant,bakery
"""

import argparse
import os
import sys
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from website_lead_agent.scanner import GoogleMapsScanner
from website_lead_agent.checker import WebsiteChecker
from website_lead_agent.reports import LeadReportGenerator


console = Console()


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Find businesses that need a website or website improvement."
    )
    parser.add_argument(
        "--location",
        required=True,
        help='Search center (address or "lat,lng").',
    )
    parser.add_argument(
        "--radius",
        type=int,
        default=5000,
        help="Search radius in meters (default: 5000).",
    )
    parser.add_argument(
        "--types",
        help="Comma-separated business types to search (default: all common types).",
    )
    parser.add_argument(
        "--output-dir",
        default="reports_output",
        help="Directory for report output (default: reports_output).",
    )
    parser.add_argument(
        "--skip-website-check",
        action="store_true",
        help="Skip checking website quality (faster, only finds missing websites).",
    )

    args = parser.parse_args()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        console.print(
            "[red]Error:[/red] Set GOOGLE_MAPS_API_KEY in your .env file or environment."
        )
        sys.exit(1)

    business_types = args.types.split(",") if args.types else None

    # Step 1: Scan Google Maps
    console.print(f"\n[bold blue]Scanning Google Maps[/bold blue] around '{args.location}'...")
    scanner = GoogleMapsScanner(api_key)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Searching for businesses...", total=None)
        businesses = scanner.search_area(
            location=args.location,
            radius_meters=args.radius,
            business_types=business_types,
        )
        progress.update(task, description=f"Found {len(businesses)} businesses")

    if not businesses:
        console.print("[yellow]No businesses found in this area.[/yellow]")
        sys.exit(0)

    # Step 2: Enrich with details (website, phone, etc.)
    console.print(f"[bold blue]Fetching details[/bold blue] for {len(businesses)} businesses...")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Enriching business data...", total=None)
        businesses = scanner.enrich_businesses(businesses)
        progress.update(task, description="Details fetched")

    no_website = scanner.filter_no_website(businesses)
    has_website = [b for b in businesses if b.has_website]

    console.print(f"  - {len(no_website)} businesses have [red]no website[/red]")
    console.print(f"  - {len(has_website)} businesses have a website")

    # Step 3: Check website quality
    website_reports = {}
    if not args.skip_website_check and has_website:
        console.print(f"\n[bold blue]Checking website quality[/bold blue] for {len(has_website)} sites...")
        checker = WebsiteChecker()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Analyzing websites...", total=len(has_website))
            for biz in has_website:
                if biz.website:
                    report = checker.check(biz.website)
                    website_reports[biz.website] = report
                    if report.needs_improvement:
                        biz.needs_improvement = True
                progress.advance(task)

    # Step 4: Generate report
    console.print(f"\n[bold blue]Generating report...[/bold blue]")
    reporter = LeadReportGenerator(output_dir=args.output_dir)
    report_path = reporter.generate(businesses, website_reports, args.location)
    reporter.print_summary(businesses, website_reports)

    # Step 5: Display top leads
    _display_top_leads(businesses, website_reports)

    console.print(f"\n[green]Report saved to:[/green] {report_path}")
    console.print(
        f"[dim]JSON report also saved in the same directory.[/dim]\n"
    )


def _display_top_leads(
    businesses: list,
    website_reports: dict,
):
    """Display a rich table of top leads."""
    table = Table(title="Top Leads (No Website or Poor Quality)")
    table.add_column("Business", style="bold")
    table.add_column("Address")
    table.add_column("Phone")
    table.add_column("Website", style="dim")
    table.add_column("Score", justify="center")
    table.add_column("Issue", style="red")

    count = 0
    for biz in businesses:
        if count >= 20:
            break

        if not biz.has_website:
            table.add_row(
                biz.name,
                biz.address,
                biz.phone or "N/A",
                "None",
                "-",
                "No website",
            )
            count += 1
        elif biz.website and biz.website in website_reports:
            report = website_reports[biz.website]
            if report.needs_improvement:
                score_str = str(report.score)
                score_style = "red" if report.score < 40 else "yellow"
                table.add_row(
                    biz.name,
                    biz.address,
                    biz.phone or "N/A",
                    biz.website,
                    f"[{score_style}]{score_str}[/{score_style}]",
                    report.issues[0] if report.issues else "Low quality",
                )
                count += 1

    if count > 0:
        console.print(table)
    else:
        console.print("[green]No leads found - all businesses have decent websites![/green]")


if __name__ == "__main__":
    main()
