-- Migration: Expand known_dockets schema for comprehensive multi-state metadata
-- This standardizes docket data across all state PSC websites

-- Add new columns to known_dockets
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS utility_type VARCHAR(50);  -- Electric, Gas, Water, Telephone, Multi
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS industry VARCHAR(50);  -- Alternative name used by some states (GA)
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS description TEXT;  -- Longer description/summary
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS filing_party VARCHAR(300);  -- Who filed (may differ from utility)
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS decision_date DATE;  -- When case was decided/closed
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS last_activity_date DATE;  -- Most recent filing/activity
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS docket_type VARCHAR(100);  -- Rate Case, Merger, Certificate, Complaint, Rulemaking, Investigation
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS sub_type VARCHAR(100);  -- More specific categorization
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS assigned_commissioner VARCHAR(200);
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS assigned_judge VARCHAR(200);  -- ALJ/Hearing Examiner
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS related_dockets JSONB DEFAULT '[]';  -- Array of related docket IDs
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS parties JSONB DEFAULT '[]';  -- Array of party names/roles
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS documents_url VARCHAR(500);  -- Direct link to documents list
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS documents_count INTEGER;
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS decision_summary TEXT;  -- Brief summary of outcome
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS amount_requested NUMERIC(15, 2);  -- For rate cases
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS amount_approved NUMERIC(15, 2);
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';  -- Catch-all for state-specific fields
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS verification_status VARCHAR(20) DEFAULT 'unverified';  -- unverified, verified, stale
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP;

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_known_dockets_utility_type ON known_dockets(utility_type);
CREATE INDEX IF NOT EXISTS idx_known_dockets_status ON known_dockets(status);
CREATE INDEX IF NOT EXISTS idx_known_dockets_filing_date ON known_dockets(filing_date);
CREATE INDEX IF NOT EXISTS idx_known_dockets_docket_type ON known_dockets(docket_type);
CREATE INDEX IF NOT EXISTS idx_known_dockets_verification ON known_dockets(verification_status);

-- Create a state_psc_configs table for scraper configuration
CREATE TABLE IF NOT EXISTS state_psc_configs (
    id SERIAL PRIMARY KEY,
    state_code VARCHAR(2) UNIQUE NOT NULL,
    state_name VARCHAR(100) NOT NULL,
    commission_name VARCHAR(200),
    commission_abbreviation VARCHAR(20),

    -- URLs
    website_url VARCHAR(500),
    docket_search_url VARCHAR(500),
    docket_detail_url_template VARCHAR(500),  -- e.g., "https://psc.ga.gov/...?docketId={docket}"
    documents_url_template VARCHAR(500),

    -- Scraper configuration
    scraper_type VARCHAR(50),  -- html, api, aspx, js_rendered
    requires_session BOOLEAN DEFAULT FALSE,
    rate_limit_ms INTEGER DEFAULT 1000,

    -- Field mappings (how to extract data from pages)
    field_mappings JSONB DEFAULT '{}',  -- Maps our fields to their HTML selectors/patterns

    -- Docket format info
    docket_format_regex VARCHAR(200),  -- Regex to validate docket numbers
    docket_format_example VARCHAR(50),  -- e.g., "2024-00123-EL"

    -- Status
    enabled BOOLEAN DEFAULT FALSE,
    last_scrape_at TIMESTAMP,
    last_error TEXT,
    dockets_count INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert initial state configurations
INSERT INTO state_psc_configs (state_code, state_name, commission_name, commission_abbreviation,
    website_url, docket_search_url, docket_detail_url_template, scraper_type, enabled, field_mappings)
VALUES
    ('GA', 'Georgia', 'Georgia Public Service Commission', 'GA PSC',
     'https://psc.ga.gov',
     'https://psc.ga.gov/facts-advanced-search/',
     'https://psc.ga.gov/facts-advanced-search/docket/?docketId={docket}',
     'html', TRUE,
     '{"title": "h6:contains(Title) + text", "industry": "h6:contains(Industry) + text", "filing_date": "h6:contains(Date) + text", "status": "h6:contains(Status) + text"}'::jsonb),

    ('TX', 'Texas', 'Public Utility Commission of Texas', 'TX PUC',
     'https://www.puc.texas.gov',
     'https://interchange.puc.texas.gov/Search/Filings',
     'https://interchange.puc.texas.gov/search/documents/?controlNumber={docket}&itemNumber=1',
     'html', TRUE,
     '{"title": "strong:contains(Case Style)", "filing_party": "strong:contains(Filing Party)", "filing_date": "strong:contains(File Stamp)", "utility_type": "pdf_checkbox"}'::jsonb),

    ('FL', 'Florida', 'Florida Public Service Commission', 'FL PSC',
     'https://www.floridapsc.com',
     'https://www.floridapsc.com/ClerkOffice/DocketSearch',
     'https://www.floridapsc.com/ClerkOffice/DocketFiling?docket={docket}',
     'html', FALSE,
     '{}'::jsonb),

    ('OH', 'Ohio', 'Public Utilities Commission of Ohio', 'PUCO',
     'https://puco.ohio.gov',
     'https://dis.puc.state.oh.us/CaseSearch.aspx',
     'https://dis.puc.state.oh.us/CaseRecord.aspx?CaseNo={docket}',
     'aspx', FALSE,
     '{}'::jsonb),

    ('CA', 'California', 'California Public Utilities Commission', 'CPUC',
     'https://www.cpuc.ca.gov',
     'https://apps.cpuc.ca.gov/apex/f?p=401:1',
     'https://apps.cpuc.ca.gov/apex/f?p=401:56::::56:P56_PROCEEDING_ID:{docket}',
     'js_rendered', FALSE,
     '{}'::jsonb),

    ('NY', 'New York', 'New York Public Service Commission', 'NY PSC',
     'https://www.dps.ny.gov',
     'https://documents.dps.ny.gov/public/MatterManagement/CaseMaster.aspx',
     'https://documents.dps.ny.gov/public/MatterManagement/CaseMaster.aspx?MatterCaseNo={docket}',
     'aspx', FALSE,
     '{}'::jsonb),

    ('PA', 'Pennsylvania', 'Pennsylvania Public Utility Commission', 'PA PUC',
     'https://www.puc.pa.gov',
     'https://www.puc.pa.gov/docket/',
     'https://www.puc.pa.gov/search/document-search/?Criteria=%22{docket}%22',
     'html', FALSE,
     '{}'::jsonb),

    ('IL', 'Illinois', 'Illinois Commerce Commission', 'ICC',
     'https://www.icc.illinois.gov',
     'https://www.icc.illinois.gov/docket/',
     'https://www.icc.illinois.gov/docket/P{docket}',
     'html', FALSE,
     '{}'::jsonb)

ON CONFLICT (state_code) DO UPDATE SET
    docket_detail_url_template = EXCLUDED.docket_detail_url_template,
    field_mappings = EXCLUDED.field_mappings,
    updated_at = CURRENT_TIMESTAMP;

-- Create docket_verifications table to track verification attempts
CREATE TABLE IF NOT EXISTS docket_verifications (
    id SERIAL PRIMARY KEY,
    docket_id INTEGER REFERENCES known_dockets(id) ON DELETE CASCADE,
    extraction_id INTEGER,  -- If verified from an extraction
    state_code VARCHAR(2) NOT NULL,
    docket_number VARCHAR(50) NOT NULL,

    -- Verification result
    verified BOOLEAN NOT NULL,
    source_url VARCHAR(500),

    -- Scraped data
    scraped_title TEXT,
    scraped_utility_type VARCHAR(50),
    scraped_company VARCHAR(300),
    scraped_filing_date DATE,
    scraped_status VARCHAR(50),
    scraped_metadata JSONB DEFAULT '{}',

    -- Tracking
    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT,

    UNIQUE(state_code, docket_number, verified_at)
);

CREATE INDEX IF NOT EXISTS idx_docket_verifications_docket ON docket_verifications(docket_id);
CREATE INDEX IF NOT EXISTS idx_docket_verifications_lookup ON docket_verifications(state_code, docket_number);

-- Add comment explaining the schema
COMMENT ON TABLE known_dockets IS 'Authoritative docket records with metadata scraped from state PSC websites';
COMMENT ON COLUMN known_dockets.utility_type IS 'Primary utility type: Electric, Gas, Water, Telephone, Multi';
COMMENT ON COLUMN known_dockets.docket_type IS 'Case category: Rate Case, Merger, Certificate, Complaint, Rulemaking, Investigation';
COMMENT ON COLUMN known_dockets.verification_status IS 'Data freshness: unverified (never checked), verified (confirmed on source), stale (source changed)';
COMMENT ON COLUMN known_dockets.metadata IS 'State-specific fields that dont fit standard schema';

COMMENT ON TABLE state_psc_configs IS 'Configuration for each state PSC scraper including URLs and field mappings';
COMMENT ON TABLE docket_verifications IS 'History of verification attempts for dockets, useful for tracking data freshness';
