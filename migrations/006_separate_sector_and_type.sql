-- Migration 006: Separate utility_sector from docket_type
-- These are different concepts:
-- - utility_sector: Industry (electric, gas, water, telecom)
-- - docket_type: Proceeding type (rate_case, application, complaint, investigation, rulemaking)

-- Add new columns to known_dockets
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS docket_type VARCHAR(50);
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS company_code VARCHAR(20);
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS raw_prefix VARCHAR(20);
ALTER TABLE known_dockets ADD COLUMN IF NOT EXISTS raw_suffix VARCHAR(20);

-- Add comments explaining the distinction
COMMENT ON COLUMN known_dockets.utility_type IS 'Industry/utility sector: electric, gas, water, telecom. From scraper (authoritative) or parsed from docket ID.';
COMMENT ON COLUMN known_dockets.docket_type IS 'Proceeding type: rate_case, application, complaint, investigation, rulemaking, tariff, certificate. Parsed from docket ID or scraped.';
COMMENT ON COLUMN known_dockets.company_code IS 'Company identifier for company-based docket systems (NC, WI, UT, MN).';
COMMENT ON COLUMN known_dockets.raw_prefix IS 'Raw prefix from docket ID before interpretation.';
COMMENT ON COLUMN known_dockets.raw_suffix IS 'Raw suffix from docket ID before interpretation.';

-- Migrate existing sector data where it was actually docket_type (CA)
-- CA used A/R/C/I which is TYPE not sector
UPDATE known_dockets
SET docket_type = CASE
    WHEN sector = 'application' THEN 'application'
    WHEN sector = 'complaint' THEN 'complaint'
    WHEN sector = 'investigation' THEN 'investigation'
    WHEN sector = 'rulemaking' THEN 'rulemaking'
    ELSE NULL
END,
sector = NULL
WHERE state_code = 'CA' AND sector IN ('application', 'complaint', 'investigation', 'rulemaking');

-- Rename sector to utility_sector for clarity (if column exists and utility_type doesn't)
-- Note: This is a careful migration - only run if the schema is in the expected state
-- ALTER TABLE known_dockets RENAME COLUMN sector TO utility_sector;

-- Add extracted_dockets columns for parser output
ALTER TABLE extracted_dockets ADD COLUMN IF NOT EXISTS parsed_year INTEGER;
ALTER TABLE extracted_dockets ADD COLUMN IF NOT EXISTS parsed_utility_sector VARCHAR(50);
ALTER TABLE extracted_dockets ADD COLUMN IF NOT EXISTS parsed_docket_type VARCHAR(50);
ALTER TABLE extracted_dockets ADD COLUMN IF NOT EXISTS parsed_company_code VARCHAR(20);

-- Create index on new columns
CREATE INDEX IF NOT EXISTS idx_known_dockets_docket_type ON known_dockets(docket_type);
CREATE INDEX IF NOT EXISTS idx_known_dockets_company_code ON known_dockets(company_code);

-- Add docket_type values as enum reference
COMMENT ON TABLE known_dockets IS 'Valid docket_type values: rate_case, application, complaint, investigation, rulemaking, tariff, certificate, petition, inquiry, general, other';
