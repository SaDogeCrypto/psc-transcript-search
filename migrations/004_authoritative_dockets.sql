-- Migration: Authoritative Dockets & Fuzzy Matching
-- Adds known_dockets table for authoritative PSC data
-- Adds docket_sources table for tracking scraper sources
-- Updates dockets table with confidence and matching fields

-- ============================================================================
-- NEW TABLE: known_dockets
-- Authoritative docket data scraped directly from PSC websites
-- ============================================================================

CREATE TABLE IF NOT EXISTS known_dockets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identity
    state_code VARCHAR(2) NOT NULL,
    docket_number VARCHAR(50) NOT NULL,           -- Raw: "20250035-GU"
    normalized_id VARCHAR(60) NOT NULL UNIQUE,    -- "FL-20250035-GU"

    -- Parsed components (for filtering)
    year INTEGER,
    case_number INTEGER,
    suffix VARCHAR(10),                           -- "GU", "EU", "WU", etc.
    sector VARCHAR(20),                           -- "gas", "electric", "water", "telecom"

    -- Metadata from PSC
    title TEXT,                                   -- Official case title
    utility_name VARCHAR(200),
    filing_date DATE,
    status VARCHAR(50),                           -- "open", "closed", "pending"
    case_type VARCHAR(100),                       -- "Rate Case", "Complaint", "Certificate"

    -- Source tracking
    source_url VARCHAR(500),
    scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(state_code, docket_number)
);

CREATE INDEX IF NOT EXISTS idx_known_dockets_state ON known_dockets(state_code);
CREATE INDEX IF NOT EXISTS idx_known_dockets_sector ON known_dockets(sector);
CREATE INDEX IF NOT EXISTS idx_known_dockets_utility ON known_dockets(utility_name);
CREATE INDEX IF NOT EXISTS idx_known_dockets_status ON known_dockets(status);
CREATE INDEX IF NOT EXISTS idx_known_dockets_year ON known_dockets(year);


-- ============================================================================
-- NEW TABLE: docket_sources
-- Track which states have docket scrapers enabled
-- ============================================================================

CREATE TABLE IF NOT EXISTS docket_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    state_code VARCHAR(2) NOT NULL UNIQUE,
    state_name VARCHAR(100) NOT NULL,
    commission_name VARCHAR(200),
    search_url VARCHAR(500),
    scraper_type VARCHAR(50),                    -- "html_table", "api_json", "aspx_form"
    enabled BOOLEAN DEFAULT 1,
    last_scraped_at DATETIME,
    last_scrape_count INTEGER,
    last_error TEXT,
    scrape_frequency_hours INTEGER DEFAULT 168,  -- Weekly by default
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Seed with all US states
INSERT OR IGNORE INTO docket_sources (state_code, state_name, commission_name, search_url, scraper_type, enabled) VALUES
('AL', 'Alabama', 'Alabama Public Service Commission', 'https://www.psc.alabama.gov/case-search', NULL, 0),
('AK', 'Alaska', 'Regulatory Commission of Alaska', 'https://rca.alaska.gov/', NULL, 0),
('AZ', 'Arizona', 'Arizona Corporation Commission', 'https://docket.acc.az.gov/', NULL, 0),
('AR', 'Arkansas', 'Arkansas Public Service Commission', 'https://www.apscservices.info/efilings/', NULL, 0),
('CA', 'California', 'California Public Utilities Commission', 'https://apps.cpuc.ca.gov/apex/f?p=401:1', 'api_json', 1),
('CO', 'Colorado', 'Colorado Public Utilities Commission', 'https://www.dora.state.co.us/pls/efi/efi.homepage', NULL, 0),
('CT', 'Connecticut', 'Connecticut PURA', 'https://www.dpuc.state.ct.us/dockcurr.nsf', NULL, 0),
('DE', 'Delaware', 'Delaware Public Service Commission', 'https://depsc.delaware.gov/dockets/', NULL, 0),
('DC', 'District of Columbia', 'DC Public Service Commission', 'https://edocket.dcpsc.org/public/search', NULL, 0),
('FL', 'Florida', 'Florida Public Service Commission', 'https://www.floridapsc.com/ClerkOffice/DocketFiling', 'html_table', 1),
('GA', 'Georgia', 'Georgia Public Service Commission', 'https://psc.ga.gov/search/dockets/', 'html_table', 1),
('HI', 'Hawaii', 'Hawaii Public Utilities Commission', 'https://dms.puc.hawaii.gov/dms/', NULL, 0),
('ID', 'Idaho', 'Idaho Public Utilities Commission', 'https://puc.idaho.gov/Case/', NULL, 0),
('IL', 'Illinois', 'Illinois Commerce Commission', 'https://www.icc.illinois.gov/e-docket/', NULL, 0),
('IN', 'Indiana', 'Indiana Utility Regulatory Commission', 'https://iurc.portal.in.gov/case-lookup/', NULL, 0),
('IA', 'Iowa', 'Iowa Utilities Board', 'https://efs.iowa.gov/efs/ShowDocketSearch', NULL, 0),
('KS', 'Kansas', 'Kansas Corporation Commission', 'https://kcc.ks.gov/e-filings', NULL, 0),
('KY', 'Kentucky', 'Kentucky Public Service Commission', 'https://psc.ky.gov/Case/Search', NULL, 0),
('LA', 'Louisiana', 'Louisiana Public Service Commission', 'https://lpsc.louisiana.gov/dockets', NULL, 0),
('ME', 'Maine', 'Maine Public Utilities Commission', 'https://mpuc-cms.maine.gov/CQM.Public.WebUI/Index', NULL, 0),
('MD', 'Maryland', 'Maryland Public Service Commission', 'https://www.psc.state.md.us/e-case-search/', NULL, 0),
('MA', 'Massachusetts', 'Massachusetts DPU', 'https://eeaonline.eea.state.ma.us/DPU/Fileroom', NULL, 0),
('MI', 'Michigan', 'Michigan Public Service Commission', 'https://mi-psc.force.com/s/cases', 'salesforce', 0),
('MN', 'Minnesota', 'Minnesota Public Utilities Commission', 'https://www.edockets.state.mn.us/EFiling/search', NULL, 0),
('MS', 'Mississippi', 'Mississippi Public Service Commission', 'https://www.psc.ms.gov/docket-filings', NULL, 0),
('MO', 'Missouri', 'Missouri Public Service Commission', 'https://www.efis.psc.mo.gov/mpsc/CaseList.asp', NULL, 0),
('MT', 'Montana', 'Montana Public Service Commission', 'https://psc.mt.gov/Proceedings', NULL, 0),
('NE', 'Nebraska', 'Nebraska Public Service Commission', 'https://psc.nebraska.gov/case-files', NULL, 0),
('NV', 'Nevada', 'Nevada PUC', 'https://pucweb1.state.nv.us/pucn/Dockets', NULL, 0),
('NH', 'New Hampshire', 'New Hampshire PUC', 'https://www.puc.nh.gov/regulatory/Docketbk.htm', NULL, 0),
('NJ', 'New Jersey', 'New Jersey BPU', 'https://publicaccess.bpu.state.nj.us/', NULL, 0),
('NM', 'New Mexico', 'New Mexico PRC', 'https://e-file.nmprc.state.nm.us/', NULL, 0),
('NY', 'New York', 'New York PSC', 'https://documents.dps.ny.gov/public/MatterManagement/CaseMaster.aspx', NULL, 0),
('NC', 'North Carolina', 'North Carolina Utilities Commission', 'https://starw1.ncuc.net/ncuc/portal.ncuc.net', NULL, 0),
('ND', 'North Dakota', 'North Dakota PSC', 'https://psc.nd.gov/database/cases.php', NULL, 0),
('OH', 'Ohio', 'Public Utilities Commission of Ohio', 'https://dis.puc.state.oh.us/CaseRecord.aspx', NULL, 0),
('OK', 'Oklahoma', 'Oklahoma Corporation Commission', 'https://imaging.occ.ok.gov/AP/CaseSearch', NULL, 0),
('OR', 'Oregon', 'Oregon PUC', 'https://apps.puc.state.or.us/edockets/', NULL, 0),
('PA', 'Pennsylvania', 'Pennsylvania PUC', 'https://www.puc.pa.gov/search/case-search/', NULL, 0),
('RI', 'Rhode Island', 'Rhode Island PUC', 'https://www.ripuc.ri.gov/eventsactions/docket.html', NULL, 0),
('SC', 'South Carolina', 'South Carolina PSC', 'https://dms.psc.sc.gov/Web/Dockets', NULL, 0),
('SD', 'South Dakota', 'South Dakota PUC', 'https://puc.sd.gov/Dockets/', NULL, 0),
('TN', 'Tennessee', 'Tennessee Regulatory Authority', 'https://share.tn.gov/tra/CaseManagement/', NULL, 0),
('TX', 'Texas', 'Public Utility Commission of Texas', 'https://interchange.puc.texas.gov/search/filings/', 'api_json', 1),
('UT', 'Utah', 'Utah PSC', 'https://psc.utah.gov/case-search/', NULL, 0),
('VT', 'Vermont', 'Vermont PUC', 'https://epuc.vermont.gov/', NULL, 0),
('VA', 'Virginia', 'Virginia SCC', 'https://scc.virginia.gov/docketsearch', NULL, 0),
('WA', 'Washington', 'Washington UTC', 'https://www.utc.wa.gov/casedocket', NULL, 0),
('WV', 'West Virginia', 'West Virginia PSC', 'https://www.psc.state.wv.us/scripts/WebDocket/ViewDockets.cfm', NULL, 0),
('WI', 'Wisconsin', 'Wisconsin PSC', 'https://apps.psc.wi.gov/vs/default.aspx', NULL, 0),
('WY', 'Wyoming', 'Wyoming PSC', 'https://psc.wyo.gov/case-dockets', NULL, 0);


-- ============================================================================
-- UPDATE TABLE: dockets
-- Add confidence and matching fields
-- ============================================================================

-- Link to authoritative known_docket
ALTER TABLE dockets ADD COLUMN known_docket_id INTEGER REFERENCES known_dockets(id);

-- Confidence level: verified, likely, possible, unverified
ALTER TABLE dockets ADD COLUMN confidence VARCHAR(20) DEFAULT 'unverified';

-- Match score from fuzzy matching (0.0 to 1.0)
ALTER TABLE dockets ADD COLUMN match_score FLOAT;

-- Parsed components
ALTER TABLE dockets ADD COLUMN sector VARCHAR(20);
ALTER TABLE dockets ADD COLUMN year INTEGER;

CREATE INDEX IF NOT EXISTS idx_dockets_confidence ON dockets(confidence);
CREATE INDEX IF NOT EXISTS idx_dockets_sector ON dockets(sector);
CREATE INDEX IF NOT EXISTS idx_dockets_known ON dockets(known_docket_id);
CREATE INDEX IF NOT EXISTS idx_dockets_year ON dockets(year);
