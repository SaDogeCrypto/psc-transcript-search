#!/usr/bin/env python3
"""
Migration: Expand known_dockets schema for comprehensive multi-state metadata.
Works with both SQLite and PostgreSQL.
"""
import sys
sys.path.insert(0, '.')

from sqlalchemy import text, inspect
from app.database import engine, SessionLocal

def column_exists(inspector, table_name, column_name):
    """Check if a column exists in a table."""
    columns = [c['name'] for c in inspector.get_columns(table_name)]
    return column_name in columns

def table_exists(inspector, table_name):
    """Check if a table exists."""
    return table_name in inspector.get_table_names()

def run_migration():
    """Run the schema expansion migration."""
    db = SessionLocal()
    inspector = inspect(engine)
    is_sqlite = str(engine.url).startswith('sqlite')

    print(f"Running migration on {'SQLite' if is_sqlite else 'PostgreSQL'} database...")

    try:
        # Add new columns to known_dockets
        new_columns = [
            ("utility_type", "VARCHAR(50)"),
            ("industry", "VARCHAR(50)"),
            ("description", "TEXT"),
            ("filing_party", "VARCHAR(300)"),
            ("decision_date", "DATE"),
            ("last_activity_date", "DATE"),
            ("docket_type", "VARCHAR(100)"),
            ("sub_type", "VARCHAR(100)"),
            ("assigned_commissioner", "VARCHAR(200)"),
            ("assigned_judge", "VARCHAR(200)"),
            ("related_dockets", "JSON" if is_sqlite else "JSONB"),
            ("parties", "JSON" if is_sqlite else "JSONB"),
            ("documents_url", "VARCHAR(500)"),
            ("documents_count", "INTEGER"),
            ("decision_summary", "TEXT"),
            ("amount_requested", "NUMERIC(15, 2)"),
            ("amount_approved", "NUMERIC(15, 2)"),
            ("metadata", "JSON" if is_sqlite else "JSONB"),
            ("verification_status", "VARCHAR(20) DEFAULT 'unverified'"),
            ("verified_at", "TIMESTAMP"),
        ]

        for col_name, col_type in new_columns:
            if not column_exists(inspector, 'known_dockets', col_name):
                print(f"  Adding column: known_dockets.{col_name}")
                db.execute(text(f"ALTER TABLE known_dockets ADD COLUMN {col_name} {col_type}"))
            else:
                print(f"  Column exists: known_dockets.{col_name}")

        db.commit()

        # Create state_psc_configs table
        if not table_exists(inspector, 'state_psc_configs'):
            print("  Creating table: state_psc_configs")
            json_type = "JSON" if is_sqlite else "JSONB"
            db.execute(text(f"""
                CREATE TABLE state_psc_configs (
                    id INTEGER PRIMARY KEY {'AUTOINCREMENT' if is_sqlite else ''},
                    state_code VARCHAR(2) UNIQUE NOT NULL,
                    state_name VARCHAR(100) NOT NULL,
                    commission_name VARCHAR(200),
                    commission_abbreviation VARCHAR(20),
                    website_url VARCHAR(500),
                    docket_search_url VARCHAR(500),
                    docket_detail_url_template VARCHAR(500),
                    documents_url_template VARCHAR(500),
                    scraper_type VARCHAR(50),
                    requires_session BOOLEAN DEFAULT FALSE,
                    rate_limit_ms INTEGER DEFAULT 1000,
                    field_mappings {json_type} DEFAULT '{{}}'::{'json' if is_sqlite else 'jsonb'},
                    docket_format_regex VARCHAR(200),
                    docket_format_example VARCHAR(50),
                    enabled BOOLEAN DEFAULT FALSE,
                    last_scrape_at TIMESTAMP,
                    last_error TEXT,
                    dockets_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """.replace("'{}'::json", "'{}'").replace("'{}'::jsonb", "'{}'")))
            db.commit()
        else:
            print("  Table exists: state_psc_configs")

        # Insert state configurations
        print("  Inserting state PSC configurations...")
        states = [
            ('GA', 'Georgia', 'Georgia Public Service Commission', 'GA PSC',
             'https://psc.ga.gov',
             'https://psc.ga.gov/facts-advanced-search/',
             'https://psc.ga.gov/facts-advanced-search/docket/?docketId={docket}',
             'html', True),
            ('TX', 'Texas', 'Public Utility Commission of Texas', 'TX PUC',
             'https://www.puc.texas.gov',
             'https://interchange.puc.texas.gov/Search/Filings',
             'https://interchange.puc.texas.gov/search/documents/?controlNumber={docket}&itemNumber=1',
             'html', True),
            ('FL', 'Florida', 'Florida Public Service Commission', 'FL PSC',
             'https://www.floridapsc.com',
             'https://www.floridapsc.com/ClerkOffice/DocketSearch',
             'https://www.floridapsc.com/ClerkOffice/DocketFiling?docket={docket}',
             'html', False),
            ('OH', 'Ohio', 'Public Utilities Commission of Ohio', 'PUCO',
             'https://puco.ohio.gov',
             'https://dis.puc.state.oh.us/CaseSearch.aspx',
             'https://dis.puc.state.oh.us/CaseRecord.aspx?CaseNo={docket}',
             'aspx', False),
            ('CA', 'California', 'California Public Utilities Commission', 'CPUC',
             'https://www.cpuc.ca.gov',
             'https://apps.cpuc.ca.gov/apex/f?p=401:1',
             'https://apps.cpuc.ca.gov/apex/f?p=401:56::::56:P56_PROCEEDING_ID:{docket}',
             'js_rendered', False),
            ('NY', 'New York', 'New York Public Service Commission', 'NY PSC',
             'https://www.dps.ny.gov',
             'https://documents.dps.ny.gov/public/MatterManagement/CaseMaster.aspx',
             'https://documents.dps.ny.gov/public/MatterManagement/CaseMaster.aspx?MatterCaseNo={docket}',
             'aspx', False),
            ('PA', 'Pennsylvania', 'Pennsylvania Public Utility Commission', 'PA PUC',
             'https://www.puc.pa.gov',
             'https://www.puc.pa.gov/docket/',
             'https://www.puc.pa.gov/search/document-search/?Criteria=%22{docket}%22',
             'html', False),
            ('IL', 'Illinois', 'Illinois Commerce Commission', 'ICC',
             'https://www.icc.illinois.gov',
             'https://www.icc.illinois.gov/docket/',
             'https://www.icc.illinois.gov/docket/P{docket}',
             'html', False),
        ]

        for state in states:
            existing = db.execute(text(
                "SELECT id FROM state_psc_configs WHERE state_code = :code"
            ), {"code": state[0]}).fetchone()

            if not existing:
                db.execute(text("""
                    INSERT INTO state_psc_configs
                    (state_code, state_name, commission_name, commission_abbreviation,
                     website_url, docket_search_url, docket_detail_url_template,
                     scraper_type, enabled)
                    VALUES (:code, :name, :commission, :abbrev, :website, :search, :detail, :scraper, :enabled)
                """), {
                    "code": state[0], "name": state[1], "commission": state[2], "abbrev": state[3],
                    "website": state[4], "search": state[5], "detail": state[6],
                    "scraper": state[7], "enabled": state[8]
                })
                print(f"    Added: {state[0]} - {state[1]}")
            else:
                print(f"    Exists: {state[0]} - {state[1]}")

        db.commit()

        # Create docket_verifications table
        if not table_exists(inspector, 'docket_verifications'):
            print("  Creating table: docket_verifications")
            json_type = "JSON" if is_sqlite else "JSONB"
            db.execute(text(f"""
                CREATE TABLE docket_verifications (
                    id INTEGER PRIMARY KEY {'AUTOINCREMENT' if is_sqlite else ''},
                    docket_id INTEGER REFERENCES known_dockets(id) ON DELETE CASCADE,
                    extraction_id INTEGER,
                    state_code VARCHAR(2) NOT NULL,
                    docket_number VARCHAR(50) NOT NULL,
                    verified BOOLEAN NOT NULL,
                    source_url VARCHAR(500),
                    scraped_title TEXT,
                    scraped_utility_type VARCHAR(50),
                    scraped_company VARCHAR(300),
                    scraped_filing_date DATE,
                    scraped_status VARCHAR(50),
                    scraped_metadata {json_type} DEFAULT '{{}}'::{'json' if is_sqlite else 'jsonb'},
                    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    error_message TEXT
                )
            """.replace("'{}'::json", "'{}'").replace("'{}'::jsonb", "'{}'")))
            db.commit()
        else:
            print("  Table exists: docket_verifications")

        # Create indexes (SQLite compatible)
        indexes = [
            ("idx_known_dockets_utility_type", "known_dockets", "utility_type"),
            ("idx_known_dockets_status", "known_dockets", "status"),
            ("idx_known_dockets_filing_date", "known_dockets", "filing_date"),
            ("idx_known_dockets_docket_type", "known_dockets", "docket_type"),
            ("idx_known_dockets_verification", "known_dockets", "verification_status"),
            ("idx_docket_verifications_docket", "docket_verifications", "docket_id"),
        ]

        for idx_name, table, column in indexes:
            try:
                db.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})"))
                print(f"  Index: {idx_name}")
            except Exception as e:
                if "already exists" not in str(e).lower():
                    print(f"  Index {idx_name} error: {e}")

        db.commit()
        print("\nMigration completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"\nMigration failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_migration()
