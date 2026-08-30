# Leatherback Licensing Database — Quality Report

Generated: `2026-08-30T13:28:01+00:00`

## Corpus counts

- **Registered Sources**: 94
- **Sources Complete**: 86
- **Sources Failed**: 7
- **Sources Skipped Gated**: 1
- **Pages Captured**: 288
- **Raw Agencies**: 102
- **Raw Market Participants**: 621
- **Raw Brand Strings**: 6,299
- **Raw Relationships**: 13,343
- **Raw Conference Records**: 1,819
- **Raw Evidence Records**: 19,691
- **Clean Agencies**: 94
- **Clean Brands**: 1,762
- **Clean High Confidence Brands**: 672
- **Clean Documented Brands**: 991
- **Clean Review Brands**: 99
- **Clean Relationships**: 1,920
- **Clean Evidence Records**: 3,870
- **Rejected Or Unresolved Brand Strings**: 4,537

## Interpretation

- The SQLite database contains both the complete raw crawl and the deterministic clean layer.
- `clean_brands` excludes navigation labels, fonts, countries, page metadata, article headlines, analytics components and other non-brand strings.
- The preliminary opportunity score is a triage heuristic, not the final AI-reviewed ranking.
- A portfolio listing is evidence of representation activity, not proof that travel rights are currently unencumbered.

## Sources not completed

| Source | Type | HTTP | Robots | Error |
|---|---|---:|---|---|
| Licensing International Global Directory | industry_directory |  |  | Authorized export/login required; not bypassed. |
| Pink Key Licensing | agency_portfolio |  | unknown | browser Error: Page.goto: net::ERR_NAME_NOT_RESOLVED at https://pinkkeylicensing.com/brands/
Call log:
  - navigating to "https://pinkkeylicensing.com/brands/", waiting until "domcontentloaded"
 / static ConnectionError: HTTPSConnectionPool |
| JELC | agency_portfolio |  | unknown | browser Error: Page.goto: net::ERR_NAME_NOT_RESOLVED at https://jelc.co.uk/
Call log:
  - navigating to "https://jelc.co.uk/", waiting until "domcontentloaded"
 / static ConnectionError: HTTPSConnectionPool(host='jelc.co.uk', port=443): Max |
| Glam Licensing and Consulting | agency_portfolio |  | unknown | browser TimeoutError: Page.goto: Timeout 45000ms exceeded.
Call log:
  - navigating to "https://glamlicensing.com/brands/", waiting until "domcontentloaded"
 / static ConnectionError: HTTPSConnectionPool(host='glamlicensing.com', port=443): |
| Redibra | agency_portfolio |  | unknown | browser Error: Page.goto: net::ERR_NAME_NOT_RESOLVED at https://redibra.com/
Call log:
  - navigating to "https://redibra.com/", waiting until "domcontentloaded"
 / static ConnectionError: HTTPSConnectionPool(host='redibra.com', port=443):  |
| Licensing Management International | agency_portfolio |  | unknown | browser Error: Page.goto: net::ERR_NAME_NOT_RESOLVED at https://lmiworld.com/brands/
Call log:
  - navigating to "https://lmiworld.com/brands/", waiting until "domcontentloaded"
 / static ConnectionError: HTTPSConnectionPool(host='lmiworld. |
| La Panaderia Licensing and Marketing | agency_portfolio |  | unknown | browser Error: Page.goto: net::ERR_NAME_NOT_RESOLVED at https://lapanaderialicensing.com/
Call log:
  - navigating to "https://lapanaderialicensing.com/", waiting until "domcontentloaded"
 / static ConnectionError: HTTPSConnectionPool(host= |
| KJG Licensing | agency_portfolio |  | unknown | browser Error: Page.goto: net::ERR_NAME_NOT_RESOLVED at https://kjglicensing.com/brands/
Call log:
  - navigating to "https://kjglicensing.com/brands/", waiting until "domcontentloaded"
 / static ConnectionError: HTTPSConnectionPool(host='k |