-- Migration 007: Update state scraper URLs for implemented parsers
-- This updates state_psc_configs with correct URLs for all states with working scrapers

-- First, ensure the table exists (creates if not, does nothing if exists)
CREATE TABLE IF NOT EXISTS state_psc_configs (
    id SERIAL PRIMARY KEY,
    state_code VARCHAR(2) UNIQUE NOT NULL,
    state_name VARCHAR(100) NOT NULL,
    commission_name VARCHAR(200),
    commission_abbreviation VARCHAR(20),
    website_url VARCHAR(500),
    docket_search_url VARCHAR(500),
    docket_detail_url_template VARCHAR(500),
    documents_url_template VARCHAR(500),
    scraper_type VARCHAR(50) DEFAULT 'html',
    requires_session BOOLEAN DEFAULT FALSE,
    rate_limit_ms INTEGER DEFAULT 1000,
    field_mappings JSONB DEFAULT '{}',
    docket_format_regex VARCHAR(200),
    docket_format_example VARCHAR(50),
    enabled BOOLEAN DEFAULT FALSE,
    last_scrape_at TIMESTAMP,
    last_error TEXT,
    dockets_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Georgia - working HTTP scraper
INSERT INTO state_psc_configs (state_code, state_name, commission_name, commission_abbreviation,
    website_url, docket_search_url, docket_detail_url_template, scraper_type, docket_format_example, enabled)
VALUES ('GA', 'Georgia', 'Georgia Public Service Commission', 'GPSC',
    'https://psc.ga.gov', 'https://psc.ga.gov/search/', 'https://psc.ga.gov/search/facts-docket/?docketId={docket}',
    'html', '44280', TRUE)
ON CONFLICT (state_code) DO UPDATE SET
    docket_detail_url_template = EXCLUDED.docket_detail_url_template,
    enabled = TRUE,
    updated_at = CURRENT_TIMESTAMP;

-- Texas - working HTTP scraper
INSERT INTO state_psc_configs (state_code, state_name, commission_name, commission_abbreviation,
    website_url, docket_search_url, docket_detail_url_template, scraper_type, docket_format_example, enabled)
VALUES ('TX', 'Texas', 'Public Utility Commission of Texas', 'PUCT',
    'https://www.puc.texas.gov', 'https://interchange.puc.texas.gov/search/filings/',
    'https://interchange.puc.texas.gov/search/documents/?controlNumber={docket}&itemNumber=1',
    'html', '55599', TRUE)
ON CONFLICT (state_code) DO UPDATE SET
    docket_detail_url_template = EXCLUDED.docket_detail_url_template,
    enabled = TRUE,
    updated_at = CURRENT_TIMESTAMP;

-- Florida - working Playwright scraper (new URL format)
INSERT INTO state_psc_configs (state_code, state_name, commission_name, commission_abbreviation,
    website_url, docket_search_url, docket_detail_url_template, scraper_type, docket_format_example, enabled)
VALUES ('FL', 'Florida', 'Florida Public Service Commission', 'FPSC',
    'https://www.floridapsc.com', 'https://www.floridapsc.com/clerks-office-dockets',
    'https://www.floridapsc.com/clerks-office-dockets-level2?DocketNo={docket}',
    'js_rendered', '20250035-GU', TRUE)
ON CONFLICT (state_code) DO UPDATE SET
    docket_detail_url_template = 'https://www.floridapsc.com/clerks-office-dockets-level2?DocketNo={docket}',
    scraper_type = 'js_rendered',
    enabled = TRUE,
    updated_at = CURRENT_TIMESTAMP;

-- Ohio - working Playwright scraper with Bright Data proxy support
INSERT INTO state_psc_configs (state_code, state_name, commission_name, commission_abbreviation,
    website_url, docket_search_url, docket_detail_url_template, scraper_type, docket_format_example, enabled)
VALUES ('OH', 'Ohio', 'Public Utilities Commission of Ohio', 'PUCO',
    'https://puco.ohio.gov', 'https://dis.puc.state.oh.us',
    'https://dis.puc.state.oh.us/CaseRecord.aspx?CaseNo={docket}',
    'js_rendered', '25-0594-EL-AIR', TRUE)
ON CONFLICT (state_code) DO UPDATE SET
    docket_detail_url_template = EXCLUDED.docket_detail_url_template,
    scraper_type = 'js_rendered',
    enabled = TRUE,
    updated_at = CURRENT_TIMESTAMP;

-- New York - working Playwright scraper
INSERT INTO state_psc_configs (state_code, state_name, commission_name, commission_abbreviation,
    website_url, docket_search_url, docket_detail_url_template, scraper_type, docket_format_example, enabled)
VALUES ('NY', 'New York', 'New York Public Service Commission', 'NYPSC',
    'https://dps.ny.gov', 'https://documents.dps.ny.gov/public/Common/AdvanceSearch.aspx',
    'https://documents.dps.ny.gov/public/MatterManagement/CaseMaster.aspx?MatterCaseNo={docket}',
    'js_rendered', '24-E-0314', TRUE)
ON CONFLICT (state_code) DO UPDATE SET
    docket_detail_url_template = EXCLUDED.docket_detail_url_template,
    scraper_type = 'js_rendered',
    enabled = TRUE,
    updated_at = CURRENT_TIMESTAMP;

-- California - working Playwright scraper (Oracle APEX app)
INSERT INTO state_psc_configs (state_code, state_name, commission_name, commission_abbreviation,
    website_url, docket_search_url, docket_detail_url_template, scraper_type, docket_format_example, enabled)
VALUES ('CA', 'California', 'California Public Utilities Commission', 'CPUC',
    'https://www.cpuc.ca.gov', 'https://apps.cpuc.ca.gov/apex/f?p=401:1',
    'https://apps.cpuc.ca.gov/apex/f?p=401:57:::NO:RP,57:P57_PROCEEDING_ID:{docket}',
    'js_rendered', 'A.24-07-003', TRUE)
ON CONFLICT (state_code) DO UPDATE SET
    docket_detail_url_template = EXCLUDED.docket_detail_url_template,
    scraper_type = 'js_rendered',
    enabled = TRUE,
    updated_at = CURRENT_TIMESTAMP;

-- Pennsylvania - working HTTP scraper
INSERT INTO state_psc_configs (state_code, state_name, commission_name, commission_abbreviation,
    website_url, docket_search_url, docket_detail_url_template, scraper_type, docket_format_example, enabled)
VALUES ('PA', 'Pennsylvania', 'Pennsylvania Public Utility Commission', 'PAPUC',
    'https://www.puc.pa.gov', 'https://www.puc.pa.gov/search/document-search/',
    'https://www.puc.pa.gov/docket/{docket}',
    'html', 'R-2025-3057164', TRUE)
ON CONFLICT (state_code) DO UPDATE SET
    docket_detail_url_template = EXCLUDED.docket_detail_url_template,
    enabled = TRUE,
    updated_at = CURRENT_TIMESTAMP;

-- New Jersey - working HTTP scraper (needs URL template)
INSERT INTO state_psc_configs (state_code, state_name, commission_name, commission_abbreviation,
    website_url, docket_search_url, docket_detail_url_template, scraper_type, docket_format_example, enabled)
VALUES ('NJ', 'New Jersey', 'New Jersey Board of Public Utilities', 'NJBPU',
    'https://www.nj.gov/bpu', 'https://publicaccess.bpu.state.nj.us/',
    'https://publicaccess.bpu.state.nj.us/CaseActivity.aspx?case={docket}',
    'html', 'ER25040190', TRUE)
ON CONFLICT (state_code) DO UPDATE SET
    docket_detail_url_template = 'https://publicaccess.bpu.state.nj.us/CaseActivity.aspx?case={docket}',
    enabled = TRUE,
    updated_at = CURRENT_TIMESTAMP;

-- Washington - working HTTP scraper
INSERT INTO state_psc_configs (state_code, state_name, commission_name, commission_abbreviation,
    website_url, docket_search_url, docket_detail_url_template, scraper_type, docket_format_example, enabled)
VALUES ('WA', 'Washington', 'Washington Utilities and Transportation Commission', 'WUTC',
    'https://www.utc.wa.gov', 'https://www.utc.wa.gov/documents-and-proceedings/dockets',
    'https://www.utc.wa.gov/casedocket/{docket}',
    'html', 'UE-210223', TRUE)
ON CONFLICT (state_code) DO UPDATE SET
    docket_detail_url_template = EXCLUDED.docket_detail_url_template,
    enabled = TRUE,
    updated_at = CURRENT_TIMESTAMP;

-- Colorado - working HTTP scraper (needs correct URL template)
INSERT INTO state_psc_configs (state_code, state_name, commission_name, commission_abbreviation,
    website_url, docket_search_url, docket_detail_url_template, scraper_type, docket_format_example, enabled)
VALUES ('CO', 'Colorado', 'Colorado Public Utilities Commission', 'COPUC',
    'https://puc.colorado.gov', 'https://www.dora.state.co.us/pls/efi/EFI.Show_Docket',
    'https://www.dora.state.co.us/pls/efi/EFI_Search_UI.Show_Decision_List?p_dec_num={docket}',
    'html', '21A-0625EG', TRUE)
ON CONFLICT (state_code) DO UPDATE SET
    docket_detail_url_template = 'https://www.dora.state.co.us/pls/efi/EFI_Search_UI.Show_Decision_List?p_dec_num={docket}',
    enabled = TRUE,
    updated_at = CURRENT_TIMESTAMP;

-- North Carolina - working HTTP scraper
INSERT INTO state_psc_configs (state_code, state_name, commission_name, commission_abbreviation,
    website_url, docket_search_url, docket_detail_url_template, scraper_type, docket_format_example, enabled)
VALUES ('NC', 'North Carolina', 'North Carolina Utilities Commission', 'NCUC',
    'https://www.ncuc.gov', 'https://starw1.ncuc.gov/NCUC/PSC/DocketSearch.aspx',
    'https://starw1.ncuc.gov/NCUC/page/docket-docs/PSC/DocketDetails.aspx?DocketId={docket}',
    'html', 'E-2,SUB 1300', TRUE)
ON CONFLICT (state_code) DO UPDATE SET
    docket_detail_url_template = EXCLUDED.docket_detail_url_template,
    enabled = TRUE,
    updated_at = CURRENT_TIMESTAMP;

-- South Carolina - working HTTP scraper
INSERT INTO state_psc_configs (state_code, state_name, commission_name, commission_abbreviation,
    website_url, docket_search_url, docket_detail_url_template, scraper_type, docket_format_example, enabled)
VALUES ('SC', 'South Carolina', 'Public Service Commission of South Carolina', 'SCPSC',
    'https://www.psc.sc.gov', 'https://dms.psc.sc.gov/',
    'https://dms.psc.sc.gov/Web/Dockets/{docket}',
    'html', '2023-189-E', TRUE)
ON CONFLICT (state_code) DO UPDATE SET
    docket_detail_url_template = 'https://dms.psc.sc.gov/Web/Dockets/{docket}',
    enabled = TRUE,
    updated_at = CURRENT_TIMESTAMP;

-- Add remaining states as disabled (for future implementation)
-- These have parsers in development or need research

INSERT INTO state_psc_configs (state_code, state_name, commission_name, enabled)
VALUES
    ('IL', 'Illinois', 'Illinois Commerce Commission', FALSE),
    ('MI', 'Michigan', 'Michigan Public Service Commission', FALSE),
    ('VA', 'Virginia', 'Virginia State Corporation Commission', FALSE),
    ('MN', 'Minnesota', 'Minnesota Public Utilities Commission', FALSE),
    ('OR', 'Oregon', 'Oregon Public Utility Commission', FALSE),
    ('SD', 'South Dakota', 'South Dakota Public Utilities Commission', FALSE),
    ('AZ', 'Arizona', 'Arizona Corporation Commission', FALSE),
    ('LA', 'Louisiana', 'Louisiana Public Service Commission', FALSE),
    ('MO', 'Missouri', 'Missouri Public Service Commission', FALSE),
    ('WV', 'West Virginia', 'Public Service Commission of West Virginia', FALSE),
    ('WI', 'Wisconsin', 'Public Service Commission of Wisconsin', FALSE)
ON CONFLICT (state_code) DO NOTHING;
