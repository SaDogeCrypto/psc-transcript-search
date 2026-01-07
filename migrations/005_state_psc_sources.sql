-- Migration 005: Comprehensive State PSC Sources
-- All 50 states + DC with docket format information and website URLs

-- Drop existing table if it exists (we're replacing it with comprehensive data)
DROP TABLE IF EXISTS state_psc_sources;

CREATE TABLE state_psc_sources (
    id SERIAL PRIMARY KEY,
    state_code VARCHAR(2) NOT NULL UNIQUE,
    state_name VARCHAR(50) NOT NULL,

    -- Commission info
    commission_name VARCHAR(200) NOT NULL,
    commission_abbreviation VARCHAR(20),

    -- URLs
    website_url VARCHAR(500),
    docket_search_url VARCHAR(500),
    docket_detail_url_template VARCHAR(500),  -- Use {docket} placeholder
    documents_url_template VARCHAR(500),

    -- Docket format info
    docket_format VARCHAR(50),           -- e.g., "YY-NNNN-XX-XXX"
    docket_format_example VARCHAR(50),   -- e.g., "25-0594-EL-AIR"
    docket_format_regex VARCHAR(200),
    has_year_in_id BOOLEAN DEFAULT FALSE,
    has_sector_in_id BOOLEAN DEFAULT FALSE,
    has_type_in_id BOOLEAN DEFAULT FALSE,
    format_category VARCHAR(20),          -- A=rich, B=year+seq, C=sequential, D=company

    -- Scraping config
    scraper_type VARCHAR(20) DEFAULT 'html',  -- html, api, aspx, js_rendered
    requires_session BOOLEAN DEFAULT FALSE,
    rate_limit_ms INTEGER DEFAULT 1000,

    -- Status
    scraper_enabled BOOLEAN DEFAULT FALSE,
    parser_enabled BOOLEAN DEFAULT FALSE,
    metadata_scraper_enabled BOOLEAN DEFAULT FALSE,

    -- Tracking
    last_scraped_at TIMESTAMP,
    last_error TEXT,
    notes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert all 50 states + DC
INSERT INTO state_psc_sources (
    state_code, state_name, commission_name, commission_abbreviation,
    website_url, docket_search_url, docket_detail_url_template,
    docket_format, docket_format_example,
    has_year_in_id, has_sector_in_id, has_type_in_id, format_category,
    scraper_type, parser_enabled, notes
) VALUES
-- TIER 1: Implemented states with full support
('GA', 'Georgia', 'Georgia Public Service Commission', 'GPSC',
 'https://psc.ga.gov', 'https://psc.ga.gov/search/', 'https://psc.ga.gov/search/facts-docket/?docketId={docket}',
 'NNNNN', '44280',
 FALSE, FALSE, FALSE, 'C',
 'html', TRUE, 'Sequential IDs only. Industry from page scraping.'),

('TX', 'Texas', 'Public Utility Commission of Texas', 'PUCT',
 'https://www.puc.texas.gov', 'https://interchange.puc.texas.gov/search/filings/', 'https://interchange.puc.texas.gov/search/documents/?controlNumber={docket}&itemNumber=1',
 'NNNNN', '55599',
 FALSE, FALSE, FALSE, 'C',
 'html', TRUE, 'Control numbers. Sector from PDF checkbox extraction.'),

('CA', 'California', 'California Public Utilities Commission', 'CPUC',
 'https://www.cpuc.ca.gov', 'https://apps.cpuc.ca.gov/apex/f?p=401:1', 'https://apps.cpuc.ca.gov/apex/f?p=401:56::::56:P56_PROCEEDING_ID:{docket}',
 'X.YY-MM-NNN', 'A.24-07-003',
 TRUE, FALSE, TRUE, 'B',
 'js_rendered', TRUE, 'Prefix is TYPE (A/R/C/I) not sector. Sector from page.'),

('FL', 'Florida', 'Florida Public Service Commission', 'FPSC',
 'https://www.floridapsc.com', 'https://www.floridapsc.com/ClerkOffice', 'https://www.floridapsc.com/ClerkOffice/DocketFiling?docket={docket}',
 'YYYYNNNN-XX', '20250035-GU',
 TRUE, TRUE, FALSE, 'A',
 'html', TRUE, 'Rich format with sector suffix (EU/GU/WU/TU).'),

('OH', 'Ohio', 'Public Utilities Commission of Ohio', 'PUCO',
 'https://puco.ohio.gov', 'https://dis.puc.state.oh.us', 'https://dis.puc.state.oh.us/CaseRecord.aspx?CaseNo={docket}',
 'YY-NNNN-XX-XXX', '25-0594-EL-AIR',
 TRUE, TRUE, TRUE, 'A',
 'aspx', TRUE, 'Richest format: year, sector (EL/GA/WW), type (AIR/SSO/ATA).'),

('NC', 'North Carolina', 'North Carolina Utilities Commission', 'NCUC',
 'https://www.ncuc.gov', 'https://starw1.ncuc.gov/NCUC/PSC/DocketSearch.aspx', 'https://starw1.ncuc.gov/NCUC/page/docket-docs/PSC/DocketDetails.aspx?DocketId={docket}',
 'X-N,SUB NNN', 'E-2,SUB 1300',
 FALSE, TRUE, FALSE, 'D',
 'aspx', TRUE, 'Company-based format. E-2 = Duke Energy, E-7 = Duke Progress.'),

-- TIER 2: High-value markets with known formats
('NY', 'New York', 'New York Public Service Commission', 'NYPSC',
 'https://dps.ny.gov', 'https://documents.dps.ny.gov/public/Common/AdvanceSearch.aspx', 'https://documents.dps.ny.gov/public/MatterManagement/CaseMaster.aspx?MatterCaseNo={docket}',
 'YY-X-NNNN', '24-E-0314',
 TRUE, TRUE, FALSE, 'A',
 'aspx', TRUE, 'Year + sector (E/G/W/C/M) + sequence.'),

('PA', 'Pennsylvania', 'Pennsylvania Public Utility Commission', 'PAPUC',
 'https://www.puc.pa.gov', 'https://www.puc.pa.gov/search/document-search/', 'https://www.puc.pa.gov/docket/{docket}',
 'X-YYYY-NNNNNNN', 'R-2025-3057164',
 TRUE, FALSE, TRUE, 'B',
 'html', TRUE, 'Type prefix (R=rate, C=complaint, M=misc).'),

('NJ', 'New Jersey', 'New Jersey Board of Public Utilities', 'NJBPU',
 'https://www.nj.gov/bpu', 'https://publicaccess.bpu.state.nj.us/', NULL,
 'XXYYMMNNNNN', 'ER25040190',
 TRUE, TRUE, TRUE, 'A',
 'html', TRUE, 'Dense format: sector+type+year+month+seq (ER=Electric Rate).'),

('WA', 'Washington', 'Washington Utilities and Transportation Commission', 'WUTC',
 'https://www.utc.wa.gov', 'https://www.utc.wa.gov/documents-and-proceedings/dockets', 'https://www.utc.wa.gov/casedocket/{docket}',
 'XX-YYNNNN', 'UE-210223',
 TRUE, TRUE, FALSE, 'A',
 'html', TRUE, 'Sector prefix (UE/UG/UT) + year + sequence.'),

('CO', 'Colorado', 'Colorado Public Utilities Commission', 'COPUC',
 'https://puc.colorado.gov', 'https://www.dora.state.co.us/pls/efi/EFI.Show_Docket', NULL,
 'YYX-NNNN[XX]', '21A-0625EG',
 TRUE, TRUE, TRUE, 'A',
 'html', TRUE, 'Type code (A/C/I/R) + optional sector suffix (E/G/EG).'),

('IL', 'Illinois', 'Illinois Commerce Commission', 'ICC',
 'https://www.icc.illinois.gov', 'https://www.icc.illinois.gov/docket/', NULL,
 '[P]YYYY-NNNN', 'P2025-0383',
 TRUE, FALSE, TRUE, 'B',
 'html', FALSE, 'Optional P prefix + year + sequence.'),

('MI', 'Michigan', 'Michigan Public Service Commission', 'MPSC',
 'https://www.michigan.gov/mpsc', 'https://mi-psc.my.site.com/s/', NULL,
 'U-NNNNN', 'U-21567',
 FALSE, TRUE, FALSE, 'D',
 'html', FALSE, 'U prefix indicates utility. Sequential numbering.'),

('VA', 'Virginia', 'Virginia State Corporation Commission', 'VSCC',
 'https://scc.virginia.gov', 'https://www.scc.virginia.gov/docketsearch', NULL,
 'XXX-YYYY-NNNNN', 'PUR-2024-00144',
 TRUE, FALSE, TRUE, 'B',
 'html', FALSE, 'PUR prefix for utility cases.'),

('MN', 'Minnesota', 'Minnesota Public Utilities Commission', 'MNPUC',
 'https://mn.gov/puc', 'https://mn.gov/puc/edockets/', NULL,
 'XNNN/XX-YY-NNNN', 'E002/CN-23-212',
 TRUE, TRUE, TRUE, 'A',
 'html', FALSE, 'Company-based with type codes (CN=Certificate of Need).'),

('OR', 'Oregon', 'Oregon Public Utility Commission', 'OPUC',
 'https://www.oregon.gov/puc', 'https://apps.puc.state.or.us/edockets/', 'https://apps.puc.state.or.us/edockets/docket.asp?DocketID={docket}',
 'XX NNN', 'UE 439',
 FALSE, TRUE, TRUE, 'A',
 'html', TRUE, 'Sector prefix (UE/UG/UW/UM) + sequence.'),

('SC', 'South Carolina', 'Public Service Commission of South Carolina', 'SCPSC',
 'https://www.psc.sc.gov', 'https://dms.psc.sc.gov/', NULL,
 'YYYY-NNN-X', '2023-189-E',
 TRUE, TRUE, FALSE, 'A',
 'html', TRUE, 'Year + sequence + sector suffix (E/G/W/C/T).'),

('SD', 'South Dakota', 'South Dakota Public Utilities Commission', 'SDPUC',
 'https://puc.sd.gov', 'https://puc.sd.gov/Dockets/', NULL,
 'XXYY-NNN', 'EL24-011',
 TRUE, TRUE, FALSE, 'A',
 'html', TRUE, 'Sector prefix (EL/NG/TC/HP) + year + sequence.'),

-- TIER 3: Known formats, not yet implemented
('AZ', 'Arizona', 'Arizona Corporation Commission', 'AZCC',
 'https://www.azcc.gov', 'https://edocket.azcc.gov/', NULL,
 'X-NNNNNN-YY-NNNN', 'E-00000A-20-0094',
 TRUE, TRUE, FALSE, 'A',
 'html', FALSE, 'Utility type prefix + entity + year + sequence.'),

('LA', 'Louisiana', 'Louisiana Public Service Commission', 'LPSC',
 'http://www.lpsc.louisiana.gov', 'http://www.lpsc.louisiana.gov/docket_list.aspx', NULL,
 'X-NNNNN', 'U-37467',
 FALSE, TRUE, TRUE, 'A',
 'aspx', FALSE, 'Prefix indicates sector/type (U/T/S/I/R/X).'),

('MO', 'Missouri', 'Missouri Public Service Commission', 'MOPSC',
 'https://psc.mo.gov', 'https://efis.psc.mo.gov/Case', NULL,
 'XX-YYYY-NNNN', 'WC-2010-0357',
 TRUE, TRUE, FALSE, 'A',
 'html', FALSE, 'Sector prefix (E/G/W) + year + sequence.'),

('WV', 'West Virginia', 'Public Service Commission of West Virginia', 'WVPSC',
 'http://www.psc.state.wv.us', 'http://www.psc.state.wv.us/scripts/WebDocket/CaseLookup.cfm', NULL,
 'YY-NNNN-X-X', '08-1500-E-C',
 TRUE, TRUE, TRUE, 'A',
 'html', FALSE, 'Year + case + sector (E/G/W) + type (C=complaint).'),

('WI', 'Wisconsin', 'Public Service Commission of Wisconsin', 'PSCW',
 'https://psc.wi.gov', 'https://apps.psc.wi.gov/APPS/dockets/', NULL,
 'NNNN-XX-NNN', '2669-TI-100',
 FALSE, TRUE, FALSE, 'D',
 'html', FALSE, 'Utility ID + case type (ER/TI) + sequence.'),

('NH', 'New Hampshire', 'New Hampshire Public Utilities Commission', 'NHPUC',
 'https://www.puc.nh.gov', 'https://www.puc.nh.gov/virtual-file-room', NULL,
 'XX YY-NNN', 'DE 16-576',
 TRUE, TRUE, FALSE, 'A',
 'html', FALSE, 'Sector prefix (DE/DG/DW) + year + sequence.'),

('NM', 'New Mexico', 'New Mexico Public Regulation Commission', 'NMPRC',
 'https://www.prc.nm.gov', 'https://www.prc.nm.gov/case-lookup-e-docket/', NULL,
 'YY-NNNNN-XX', '23-00255-UT',
 TRUE, TRUE, FALSE, 'A',
 'html', FALSE, 'Year + sequence + suffix (UT=utility).'),

('OK', 'Oklahoma', 'Oklahoma Corporation Commission', 'OCC',
 'https://oklahoma.gov/occ', 'https://case.occ.ok.gov/', NULL,
 'XXX YYYY-NNNNNN', 'PUD 2022-000093',
 TRUE, TRUE, FALSE, 'A',
 'html', FALSE, 'PUD prefix + year + sequence.'),

('ND', 'North Dakota', 'North Dakota Public Service Commission', 'NDPSC',
 'https://www.psc.nd.gov', 'https://psc.nd.gov/public/casesearch/', NULL,
 'XX-YY-NNN', 'PU-22-001',
 TRUE, TRUE, FALSE, 'A',
 'html', FALSE, 'Prefix (PU) + year + sequence.'),

('VT', 'Vermont', 'Vermont Public Utility Commission', 'VTPUC',
 'https://puc.vermont.gov', 'https://epuc.vermont.gov/', NULL,
 'YY-NNNN-XXX', '25-2441-PET',
 TRUE, FALSE, TRUE, 'B',
 'html', FALSE, 'Year + sequence + type suffix (PET/TF/INV).'),

('UT', 'Utah', 'Utah Public Service Commission', 'UTPSC',
 'https://psc.utah.gov', 'https://psc.utah.gov/electric/dockets/', NULL,
 'YY-XXX-NN', '09-049-86',
 TRUE, FALSE, FALSE, 'D',
 'html', FALSE, 'Year + company code + sequence.'),

('WY', 'Wyoming', 'Wyoming Public Service Commission', 'WYPSC',
 'https://psc.wyo.gov', 'https://psc.wyo.gov/home/e-filings', NULL,
 'NNNNN-NNN-XX-YY', '20000-676-EA-24',
 TRUE, FALSE, TRUE, 'D',
 'html', FALSE, 'Entity + sequence + type (EA/ER/CT) + year.'),

-- TIER 4: Simple/sequential formats
('AL', 'Alabama', 'Alabama Public Service Commission', 'ALPSC',
 'https://www.psc.alabama.gov', 'https://www.psc.alabama.gov/dockets/', NULL,
 'NNNNN', '31323',
 FALSE, FALSE, FALSE, 'C',
 'html', FALSE, 'Simple sequential numbering.'),

('TN', 'Tennessee', 'Tennessee Regulatory Authority', 'TRA',
 'https://www.tn.gov/tra', 'https://tpucdockets.tn.gov/', NULL,
 'NNNNNNN', '9900335',
 FALSE, FALSE, FALSE, 'C',
 'html', FALSE, '7-digit sequential. Year may be in prefix.'),

('MD', 'Maryland', 'Maryland Public Service Commission', 'MDPSC',
 'https://www.psc.state.md.us', 'https://www.psc.state.md.us/search-results/', NULL,
 'NNNN', '9666',
 FALSE, FALSE, FALSE, 'C',
 'html', FALSE, 'Simple 4-digit sequential.'),

('IN', 'Indiana', 'Indiana Utility Regulatory Commission', 'IURC',
 'https://www.in.gov/iurc', 'https://iurc.portal.in.gov/', NULL,
 'NNNNN[-sub]', '45159',
 FALSE, FALSE, FALSE, 'C',
 'html', FALSE, '5-digit cause numbers with optional subdocket.'),

-- TIER 5: Year + sequence format (moderate info)
('KY', 'Kentucky', 'Kentucky Public Service Commission', 'KYPSC',
 'https://psc.ky.gov', 'https://psc.ky.gov/Case/Search', NULL,
 'YYYY-NNNNN', '2025-00122',
 TRUE, FALSE, FALSE, 'B',
 'html', FALSE, 'Year + sequence, no sector encoding.'),

('HI', 'Hawaii', 'Hawaii Public Utilities Commission', 'HIPUC',
 'https://puc.hawaii.gov', 'https://hpuc.my.site.com/cdms/s/search', NULL,
 'YYYY-NNNN', '2025-0167',
 TRUE, FALSE, FALSE, 'B',
 'html', FALSE, 'Year + sequence.'),

('NV', 'Nevada', 'Public Utilities Commission of Nevada', 'PUCN',
 'https://puc.nv.gov', 'https://pucweb1.state.nv.us/puc2/Dktinfo.aspx', NULL,
 'YY-NNNNN', '15-06042',
 TRUE, FALSE, FALSE, 'B',
 'html', FALSE, 'Year + sequence.'),

('ME', 'Maine', 'Maine Public Utilities Commission', 'MPUC',
 'https://www.maine.gov/mpuc', 'https://www.maine.gov/mpuc/cases/', NULL,
 'YYYY-NNNNN', '2024-00149',
 TRUE, FALSE, FALSE, 'B',
 'html', FALSE, 'Year + sequence.'),

('AK', 'Alaska', 'Regulatory Commission of Alaska', 'RCA',
 'https://rca.alaska.gov', 'https://rca.alaska.gov/RCAWeb/RCALibrary/QuickSearches.aspx', NULL,
 'X-YY-NNN', 'I-09-007',
 TRUE, FALSE, TRUE, 'B',
 'html', FALSE, 'Type prefix (I/R/TL) + year + sequence.'),

('AR', 'Arkansas', 'Arkansas Public Service Commission', 'APSC',
 'http://www.apscservices.info', 'http://www.apscservices.info/efilings/', NULL,
 'YY-NNN-X', '24-001-U',
 TRUE, FALSE, FALSE, 'B',
 'html', FALSE, 'Year + sequence + suffix.'),

('CT', 'Connecticut', 'Connecticut Public Utilities Regulatory Authority', 'PURA',
 'https://portal.ct.gov/pura', 'https://www.dpuc.state.ct.us/dockcurr.nsf', NULL,
 'YY-MM-NN', '20-07-01',
 TRUE, FALSE, FALSE, 'B',
 'html', FALSE, 'Year + month + sequence.'),

('DE', 'Delaware', 'Delaware Public Service Commission', 'DEPSC',
 'https://depsc.delaware.gov', 'https://depsc.delaware.gov/dockets/', NULL,
 'YY-NNNN', '24-0868',
 TRUE, FALSE, FALSE, 'B',
 'html', FALSE, 'Year + sequence.'),

('DC', 'District of Columbia', 'Public Service Commission of the District of Columbia', 'DCPSC',
 'https://dcpsc.org', 'https://edocket.dcpsc.org/public/search', NULL,
 'FC NNNN', 'FC 1093',
 FALSE, FALSE, TRUE, 'B',
 'html', FALSE, 'Formal Case prefix + sequence.'),

('ID', 'Idaho', 'Idaho Public Utilities Commission', 'IPUC',
 'https://puc.idaho.gov', 'https://puc.idaho.gov/case/', NULL,
 'XXX-X-YY-NN', 'IPC-E-25-15',
 TRUE, TRUE, FALSE, 'A',
 'html', FALSE, 'Company + sector (E) + year + sequence.'),

('IA', 'Iowa', 'Iowa Utilities Board', 'IUB',
 'https://iub.iowa.gov', 'https://efs.iowa.gov/efs/', NULL,
 '[prefix]-YY-NNNN', 'varies',
 TRUE, FALSE, TRUE, 'A',
 'html', FALSE, '40+ docket type prefixes.'),

('KS', 'Kansas', 'Kansas Corporation Commission', 'KCC',
 'https://kcc.ks.gov', 'https://estar.kcc.ks.gov/estar/portal/kcc/', NULL,
 'YY-XXXX-NNN-XXX', '08-WHLW-001-COC',
 TRUE, FALSE, TRUE, 'A',
 'html', FALSE, 'Year + company + sequence + type (COC/TRA).'),

('MA', 'Massachusetts', 'Massachusetts Department of Public Utilities', 'DPU',
 'https://www.mass.gov/orgs/department-of-public-utilities', 'https://eeaonline.eea.state.ma.us/DPU/Fileroom/', NULL,
 'YY-NN or YY-XXX-NN', '24-154',
 TRUE, FALSE, FALSE, 'B',
 'html', FALSE, 'Year + sequence or year + type + sequence.'),

('MS', 'Mississippi', 'Mississippi Public Service Commission', 'MSPSC',
 'https://www.psc.ms.gov', 'https://ctsportal.psc.ms.gov/portal/PSC/', NULL,
 'YYYY-XX-NNN', '2024-UA-135',
 TRUE, TRUE, FALSE, 'A',
 'html', FALSE, 'Year + code (UA) + sequence.'),

('MT', 'Montana', 'Montana Public Service Commission', 'MTPSC',
 'https://psc.mt.gov', 'http://psc2.mt.gov/Docs/ElectronicDocuments/', NULL,
 'varies', 'varies',
 FALSE, FALSE, FALSE, 'C',
 'html', FALSE, 'Format unclear from research.'),

('NE', 'Nebraska', 'Nebraska Public Service Commission', 'NPSC',
 'https://psc.nebraska.gov', 'https://psc.nebraska.gov/natural-gas/dockets', NULL,
 'XX-NNN', 'NG-124',
 FALSE, TRUE, FALSE, 'D',
 'html', FALSE, 'Type prefix (NG/MT/911) + sequence.'),

('RI', 'Rhode Island', 'Rhode Island Public Utilities Commission', 'RIPUC',
 'https://ripuc.ri.gov', 'https://ripuc.ri.gov/events-and-actions/commission-dockets', NULL,
 'YYYY-NNN-TYPE', '2022-001-XXX',
 TRUE, FALSE, TRUE, 'B',
 'html', FALSE, 'New format since June 2022. Year + seq + type.');

-- Create indexes
CREATE INDEX idx_state_psc_sources_state_code ON state_psc_sources(state_code);
CREATE INDEX idx_state_psc_sources_scraper_enabled ON state_psc_sources(scraper_enabled);
CREATE INDEX idx_state_psc_sources_format_category ON state_psc_sources(format_category);
