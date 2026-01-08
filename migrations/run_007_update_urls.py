#!/usr/bin/env python3
"""
Apply migration 007: Update state scraper URLs for implemented parsers.
Uses SQLAlchemy to work with both SQLite and PostgreSQL.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import engine, SessionLocal

# State configurations to upsert
STATE_CONFIGS = [
    # Georgia - working HTTP scraper
    {
        'state_code': 'GA',
        'state_name': 'Georgia',
        'commission_name': 'Georgia Public Service Commission',
        'commission_abbreviation': 'GPSC',
        'website_url': 'https://psc.ga.gov',
        'docket_search_url': 'https://psc.ga.gov/search/',
        'docket_detail_url_template': 'https://psc.ga.gov/search/facts-docket/?docketId={docket}',
        'scraper_type': 'html',
        'docket_format_example': '44280',
        'enabled': True
    },
    # Texas - working HTTP scraper
    {
        'state_code': 'TX',
        'state_name': 'Texas',
        'commission_name': 'Public Utility Commission of Texas',
        'commission_abbreviation': 'PUCT',
        'website_url': 'https://www.puc.texas.gov',
        'docket_search_url': 'https://interchange.puc.texas.gov/search/filings/',
        'docket_detail_url_template': 'https://interchange.puc.texas.gov/search/documents/?controlNumber={docket}&itemNumber=1',
        'scraper_type': 'html',
        'docket_format_example': '55599',
        'enabled': True
    },
    # Florida - working Playwright scraper (new URL format)
    {
        'state_code': 'FL',
        'state_name': 'Florida',
        'commission_name': 'Florida Public Service Commission',
        'commission_abbreviation': 'FPSC',
        'website_url': 'https://www.floridapsc.com',
        'docket_search_url': 'https://www.floridapsc.com/clerks-office-dockets',
        'docket_detail_url_template': 'https://www.floridapsc.com/clerks-office-dockets-level2?DocketNo={docket}',
        'scraper_type': 'js_rendered',
        'docket_format_example': '20250035-GU',
        'enabled': True
    },
    # Ohio - working Playwright scraper with Bright Data proxy
    {
        'state_code': 'OH',
        'state_name': 'Ohio',
        'commission_name': 'Public Utilities Commission of Ohio',
        'commission_abbreviation': 'PUCO',
        'website_url': 'https://puco.ohio.gov',
        'docket_search_url': 'https://dis.puc.state.oh.us',
        'docket_detail_url_template': 'https://dis.puc.state.oh.us/CaseRecord.aspx?CaseNo={docket}',
        'scraper_type': 'js_rendered',
        'docket_format_example': '25-0594-EL-AIR',
        'enabled': True
    },
    # New York - working Playwright scraper
    {
        'state_code': 'NY',
        'state_name': 'New York',
        'commission_name': 'New York Public Service Commission',
        'commission_abbreviation': 'NYPSC',
        'website_url': 'https://dps.ny.gov',
        'docket_search_url': 'https://documents.dps.ny.gov/public/Common/AdvanceSearch.aspx',
        'docket_detail_url_template': 'https://documents.dps.ny.gov/public/MatterManagement/CaseMaster.aspx?MatterCaseNo={docket}',
        'scraper_type': 'js_rendered',
        'docket_format_example': '24-E-0314',
        'enabled': True
    },
    # California - working Playwright scraper
    {
        'state_code': 'CA',
        'state_name': 'California',
        'commission_name': 'California Public Utilities Commission',
        'commission_abbreviation': 'CPUC',
        'website_url': 'https://www.cpuc.ca.gov',
        'docket_search_url': 'https://apps.cpuc.ca.gov/apex/f?p=401:1',
        'docket_detail_url_template': 'https://apps.cpuc.ca.gov/apex/f?p=401:57:::NO:RP,57:P57_PROCEEDING_ID:{docket}',
        'scraper_type': 'js_rendered',
        'docket_format_example': 'A.24-07-003',
        'enabled': True
    },
    # Pennsylvania - working HTTP scraper
    {
        'state_code': 'PA',
        'state_name': 'Pennsylvania',
        'commission_name': 'Pennsylvania Public Utility Commission',
        'commission_abbreviation': 'PAPUC',
        'website_url': 'https://www.puc.pa.gov',
        'docket_search_url': 'https://www.puc.pa.gov/search/document-search/',
        'docket_detail_url_template': 'https://www.puc.pa.gov/docket/{docket}',
        'scraper_type': 'html',
        'docket_format_example': 'R-2025-3057164',
        'enabled': True
    },
    # New Jersey - working HTTP scraper
    {
        'state_code': 'NJ',
        'state_name': 'New Jersey',
        'commission_name': 'New Jersey Board of Public Utilities',
        'commission_abbreviation': 'NJBPU',
        'website_url': 'https://www.nj.gov/bpu',
        'docket_search_url': 'https://publicaccess.bpu.state.nj.us/',
        'docket_detail_url_template': 'https://publicaccess.bpu.state.nj.us/CaseActivity.aspx?case={docket}',
        'scraper_type': 'html',
        'docket_format_example': 'ER25040190',
        'enabled': True
    },
    # Washington - working HTTP scraper
    {
        'state_code': 'WA',
        'state_name': 'Washington',
        'commission_name': 'Washington Utilities and Transportation Commission',
        'commission_abbreviation': 'WUTC',
        'website_url': 'https://www.utc.wa.gov',
        'docket_search_url': 'https://www.utc.wa.gov/documents-and-proceedings/dockets',
        'docket_detail_url_template': 'https://www.utc.wa.gov/casedocket/{docket}',
        'scraper_type': 'html',
        'docket_format_example': 'UE-210223',
        'enabled': True
    },
    # Colorado - working HTTP scraper
    {
        'state_code': 'CO',
        'state_name': 'Colorado',
        'commission_name': 'Colorado Public Utilities Commission',
        'commission_abbreviation': 'COPUC',
        'website_url': 'https://puc.colorado.gov',
        'docket_search_url': 'https://www.dora.state.co.us/pls/efi/EFI.Show_Docket',
        'docket_detail_url_template': 'https://www.dora.state.co.us/pls/efi/EFI_Search_UI.Show_Decision_List?p_dec_num={docket}',
        'scraper_type': 'html',
        'docket_format_example': '21A-0625EG',
        'enabled': True
    },
    # North Carolina - working HTTP scraper
    {
        'state_code': 'NC',
        'state_name': 'North Carolina',
        'commission_name': 'North Carolina Utilities Commission',
        'commission_abbreviation': 'NCUC',
        'website_url': 'https://www.ncuc.gov',
        'docket_search_url': 'https://starw1.ncuc.gov/NCUC/PSC/DocketSearch.aspx',
        'docket_detail_url_template': 'https://starw1.ncuc.gov/NCUC/page/docket-docs/PSC/DocketDetails.aspx?DocketId={docket}',
        'scraper_type': 'html',
        'docket_format_example': 'E-2,SUB 1300',
        'enabled': True
    },
    # South Carolina - working HTTP scraper
    {
        'state_code': 'SC',
        'state_name': 'South Carolina',
        'commission_name': 'Public Service Commission of South Carolina',
        'commission_abbreviation': 'SCPSC',
        'website_url': 'https://www.psc.sc.gov',
        'docket_search_url': 'https://dms.psc.sc.gov/',
        'docket_detail_url_template': 'https://dms.psc.sc.gov/Web/Dockets/{docket}',
        'scraper_type': 'html',
        'docket_format_example': '2023-189-E',
        'enabled': True
    },
]

def run_migration():
    """Apply the state config updates."""
    db = SessionLocal()
    try:
        # Check if table exists
        result = db.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='state_psc_configs'"
        )).fetchone()

        if not result:
            print("Table state_psc_configs does not exist. Creating...")
            db.execute(text("""
                CREATE TABLE state_psc_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    state_code VARCHAR(2) UNIQUE NOT NULL,
                    state_name VARCHAR(100) NOT NULL,
                    commission_name VARCHAR(200),
                    commission_abbreviation VARCHAR(20),
                    website_url VARCHAR(500),
                    docket_search_url VARCHAR(500),
                    docket_detail_url_template VARCHAR(500),
                    documents_url_template VARCHAR(500),
                    scraper_type VARCHAR(50) DEFAULT 'html',
                    requires_session BOOLEAN DEFAULT 0,
                    rate_limit_ms INTEGER DEFAULT 1000,
                    field_mappings TEXT DEFAULT '{}',
                    docket_format_regex VARCHAR(200),
                    docket_format_example VARCHAR(50),
                    enabled BOOLEAN DEFAULT 0,
                    last_scrape_at DATETIME,
                    last_error TEXT,
                    dockets_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            db.commit()
            print("Table created.")

        # Upsert each state config
        for config in STATE_CONFIGS:
            # Check if exists
            existing = db.execute(text(
                "SELECT id FROM state_psc_configs WHERE state_code = :code"
            ), {"code": config['state_code']}).fetchone()

            if existing:
                # Update
                db.execute(text("""
                    UPDATE state_psc_configs SET
                        state_name = :state_name,
                        commission_name = :commission_name,
                        commission_abbreviation = :commission_abbreviation,
                        website_url = :website_url,
                        docket_search_url = :docket_search_url,
                        docket_detail_url_template = :docket_detail_url_template,
                        scraper_type = :scraper_type,
                        docket_format_example = :docket_format_example,
                        enabled = :enabled,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE state_code = :state_code
                """), config)
                print(f"Updated {config['state_code']}")
            else:
                # Insert
                db.execute(text("""
                    INSERT INTO state_psc_configs (
                        state_code, state_name, commission_name, commission_abbreviation,
                        website_url, docket_search_url, docket_detail_url_template,
                        scraper_type, docket_format_example, enabled
                    ) VALUES (
                        :state_code, :state_name, :commission_name, :commission_abbreviation,
                        :website_url, :docket_search_url, :docket_detail_url_template,
                        :scraper_type, :docket_format_example, :enabled
                    )
                """), config)
                print(f"Inserted {config['state_code']}")

        db.commit()
        print(f"\nMigration complete. {len(STATE_CONFIGS)} states configured.")

        # Show summary
        result = db.execute(text(
            "SELECT state_code, enabled FROM state_psc_configs ORDER BY state_code"
        )).fetchall()
        print(f"\nEnabled states: {[r[0] for r in result if r[1]]}")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    run_migration()
