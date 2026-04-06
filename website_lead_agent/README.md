# Website Lead Agent

An AI-powered tool that scans Google Maps to find businesses that either:
1. **Don't have a website** — prime candidates for new web development projects
2. **Have a poor quality website** — candidates for redesign/improvement

## Setup

```bash
cd website_lead_agent
pip install -r requirements.txt
```

Create a `.env` file from the example:
```bash
cp .env.example .env
```

Add your [Google Maps API key](https://developers.google.com/maps/documentation/places/web-service/get-api-key) to `.env`:
```
GOOGLE_MAPS_API_KEY=your_actual_key_here
```

Your API key needs the following APIs enabled:
- Places API
- Geocoding API

## Usage

### Basic scan
```bash
python -m website_lead_agent.main --location "Lagos, Nigeria"
```

### Custom radius and business types
```bash
python -m website_lead_agent.main \
  --location "Benin City, Nigeria" \
  --radius 10000 \
  --types restaurant,bakery,hair_care
```

### Fast mode (skip website quality checks)
```bash
python -m website_lead_agent.main \
  --location "40.7128,-74.0060" \
  --skip-website-check
```

## Output

Reports are saved in `reports_output/` as both CSV and JSON:
- **CSV**: Easy to import into spreadsheets or CRM tools
- **JSON**: Includes metadata and full details

### Lead Priority Levels
| Priority | Meaning |
|----------|---------|
| **High** | No website, unreachable website, or score < 40 |
| **Medium** | Website exists but score < 60 |
| **Low** | Website is decent (score >= 60) |

### Website Quality Score (0-100)
Checks for: SSL, mobile responsiveness, meta tags, page speed, modern tech stack, and more.

## Supported Business Types

Restaurants, stores, salons, gyms, dentists, lawyers, plumbers, electricians, real estate, bakeries, cafes, and 15+ more categories.
