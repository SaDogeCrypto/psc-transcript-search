#!/usr/bin/env python3
"""Run migrations and test docket parsers."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import SessionLocal, engine

# Test the parser first (no DB needed)
print("=" * 60)
print("TESTING DOCKET PARSERS")
print("=" * 60)

from app.services.docket_parser import parse_docket, get_parser_coverage

test_cases = [
    # (state, docket_id, expected_sector, expected_type)
    ("GA", "44280", None, None),
    ("TX", "55599", None, None),
    ("FL", "20250035-GU", "gas", None),
    ("FL", "20230001-EU", "electric", None),
    ("OH", "25-0594-EL-AIR", "electric", "rate_case"),
    ("OH", "24-0508-GA-SSO", "gas", "rate_case"),
    ("CA", "A.24-07-003", None, "application"),
    ("CA", "R.23-01-007", None, "rulemaking"),
    ("CA", "I.22-03-015", None, "investigation"),
    ("NY", "24-E-0314", "electric", None),
    ("NY", "23-G-0156", "gas", None),
    ("WA", "UE-210223", "electric", None),
    ("WA", "UG-200568", "gas", None),
    ("NJ", "ER25040190", "electric", "rate_case"),
    ("NJ", "GR24030055", "gas", "rate_case"),
    ("CO", "21A-0625EG", "electric", "application"),
    ("PA", "R-2025-3057164", None, "rate_case"),
    ("PA", "C-2024-1234567", None, "complaint"),
    ("SC", "2023-189-E", "electric", None),
    ("SD", "EL24-011", "electric", None),
    ("OR", "UE 439", "electric", None),
    ("NC", "E-2,SUB 1300", "electric", None),
]

passed = 0
failed = 0

for state, docket_id, expected_sector, expected_type in test_cases:
    result = parse_docket(docket_id, state)

    sector_ok = result.utility_sector == expected_sector
    type_ok = result.docket_type == expected_type

    if sector_ok and type_ok:
        status = "PASS"
        passed += 1
    else:
        status = "FAIL"
        failed += 1

    print(f"{status}: {state} {docket_id:20} -> sector={result.utility_sector or 'None':10} type={result.docket_type or 'None':15} year={result.year}")

    if not sector_ok:
        print(f"      Expected sector: {expected_sector}, got: {result.utility_sector}")
    if not type_ok:
        print(f"      Expected type: {expected_type}, got: {result.docket_type}")

print()
print(f"Results: {passed} passed, {failed} failed out of {len(test_cases)} tests")
print()

# Show parser coverage
coverage = get_parser_coverage()
custom_parsers = [s for s, has in coverage.items() if has]
generic_parsers = [s for s, has in coverage.items() if not has]
print(f"Custom parsers ({len(custom_parsers)}): {', '.join(sorted(custom_parsers))}")
print(f"Generic parsers ({len(generic_parsers)}): {', '.join(sorted(generic_parsers))}")
print()

# Run migrations
print("=" * 60)
print("RUNNING MIGRATIONS")
print("=" * 60)

db = SessionLocal()

try:
    # Migration 005: State PSC Sources
    print("\nMigration 005: Creating state_psc_sources table...")

    # Check if table exists
    result = db.execute(text("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='state_psc_sources'
    """)).fetchone()

    if result:
        print("  Table state_psc_sources already exists, dropping...")
        db.execute(text("DROP TABLE IF EXISTS state_psc_sources"))
        db.commit()

    # Create table
    db.execute(text("""
        CREATE TABLE state_psc_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state_code VARCHAR(2) NOT NULL UNIQUE,
            state_name VARCHAR(50) NOT NULL,
            commission_name VARCHAR(200) NOT NULL,
            commission_abbreviation VARCHAR(20),
            website_url VARCHAR(500),
            docket_search_url VARCHAR(500),
            docket_detail_url_template VARCHAR(500),
            documents_url_template VARCHAR(500),
            docket_format VARCHAR(50),
            docket_format_example VARCHAR(50),
            docket_format_regex VARCHAR(200),
            has_year_in_id BOOLEAN DEFAULT FALSE,
            has_sector_in_id BOOLEAN DEFAULT FALSE,
            has_type_in_id BOOLEAN DEFAULT FALSE,
            format_category VARCHAR(20),
            scraper_type VARCHAR(20) DEFAULT 'html',
            requires_session BOOLEAN DEFAULT FALSE,
            rate_limit_ms INTEGER DEFAULT 1000,
            scraper_enabled BOOLEAN DEFAULT FALSE,
            parser_enabled BOOLEAN DEFAULT FALSE,
            metadata_scraper_enabled BOOLEAN DEFAULT FALSE,
            last_scraped_at TIMESTAMP,
            last_error TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.commit()
    print("  Created table state_psc_sources")

    # Insert data for key states
    states_data = [
        ('GA', 'Georgia', 'Georgia Public Service Commission', 'GPSC',
         'https://psc.ga.gov', 'https://psc.ga.gov/search/',
         'https://psc.ga.gov/search/facts-docket/?docketId={docket}',
         'NNNNN', '44280', False, False, False, 'C', True),
        ('TX', 'Texas', 'Public Utility Commission of Texas', 'PUCT',
         'https://www.puc.texas.gov', 'https://interchange.puc.texas.gov/search/filings/',
         'https://interchange.puc.texas.gov/search/documents/?controlNumber={docket}&itemNumber=1',
         'NNNNN', '55599', False, False, False, 'C', True),
        ('CA', 'California', 'California Public Utilities Commission', 'CPUC',
         'https://www.cpuc.ca.gov', 'https://apps.cpuc.ca.gov/apex/f?p=401:1',
         'https://apps.cpuc.ca.gov/apex/f?p=401:56::::56:P56_PROCEEDING_ID:{docket}',
         'X.YY-MM-NNN', 'A.24-07-003', True, False, True, 'B', True),
        ('FL', 'Florida', 'Florida Public Service Commission', 'FPSC',
         'https://www.floridapsc.com', 'https://www.floridapsc.com/ClerkOffice',
         'https://www.floridapsc.com/ClerkOffice/DocketFiling?docket={docket}',
         'YYYYNNNN-XX', '20250035-GU', True, True, False, 'A', True),
        ('OH', 'Ohio', 'Public Utilities Commission of Ohio', 'PUCO',
         'https://puco.ohio.gov', 'https://dis.puc.state.oh.us',
         'https://dis.puc.state.oh.us/CaseRecord.aspx?CaseNo={docket}',
         'YY-NNNN-XX-XXX', '25-0594-EL-AIR', True, True, True, 'A', True),
        ('NY', 'New York', 'New York Public Service Commission', 'NYPSC',
         'https://dps.ny.gov', 'https://documents.dps.ny.gov/public/Common/AdvanceSearch.aspx',
         'https://documents.dps.ny.gov/public/MatterManagement/CaseMaster.aspx?MatterCaseNo={docket}',
         'YY-X-NNNN', '24-E-0314', True, True, False, 'A', True),
        ('PA', 'Pennsylvania', 'Pennsylvania Public Utility Commission', 'PAPUC',
         'https://www.puc.pa.gov', 'https://www.puc.pa.gov/search/document-search/',
         'https://www.puc.pa.gov/docket/{docket}',
         'X-YYYY-NNNNNNN', 'R-2025-3057164', True, False, True, 'B', True),
        ('NJ', 'New Jersey', 'New Jersey Board of Public Utilities', 'NJBPU',
         'https://www.nj.gov/bpu', 'https://publicaccess.bpu.state.nj.us/',
         None,
         'XXYYMMNNNNN', 'ER25040190', True, True, True, 'A', True),
        ('WA', 'Washington', 'Washington Utilities and Transportation Commission', 'WUTC',
         'https://www.utc.wa.gov', 'https://www.utc.wa.gov/documents-and-proceedings/dockets',
         'https://www.utc.wa.gov/casedocket/{docket}',
         'XX-YYNNNN', 'UE-210223', True, True, False, 'A', True),
        ('NC', 'North Carolina', 'North Carolina Utilities Commission', 'NCUC',
         'https://www.ncuc.gov', 'https://starw1.ncuc.gov/NCUC/PSC/DocketSearch.aspx',
         'https://starw1.ncuc.gov/NCUC/page/docket-docs/PSC/DocketDetails.aspx?DocketId={docket}',
         'X-N,SUB NNN', 'E-2,SUB 1300', False, True, False, 'D', True),
        ('CO', 'Colorado', 'Colorado Public Utilities Commission', 'COPUC',
         'https://puc.colorado.gov', 'https://www.dora.state.co.us/pls/efi/EFI.Show_Docket',
         None,
         'YYX-NNNN[XX]', '21A-0625EG', True, True, True, 'A', True),
        ('OR', 'Oregon', 'Oregon Public Utility Commission', 'OPUC',
         'https://www.oregon.gov/puc', 'https://apps.puc.state.or.us/edockets/',
         'https://apps.puc.state.or.us/edockets/docket.asp?DocketID={docket}',
         'XX NNN', 'UE 439', False, True, True, 'A', True),
        ('SC', 'South Carolina', 'Public Service Commission of South Carolina', 'SCPSC',
         'https://www.psc.sc.gov', 'https://dms.psc.sc.gov/',
         None,
         'YYYY-NNN-X', '2023-189-E', True, True, False, 'A', True),
        ('SD', 'South Dakota', 'South Dakota Public Utilities Commission', 'SDPUC',
         'https://puc.sd.gov', 'https://puc.sd.gov/Dockets/',
         None,
         'XXYY-NNN', 'EL24-011', True, True, False, 'A', True),
    ]

    for row in states_data:
        db.execute(text("""
            INSERT INTO state_psc_sources (
                state_code, state_name, commission_name, commission_abbreviation,
                website_url, docket_search_url, docket_detail_url_template,
                docket_format, docket_format_example,
                has_year_in_id, has_sector_in_id, has_type_in_id, format_category,
                parser_enabled
            ) VALUES (
                :state_code, :state_name, :commission_name, :abbr,
                :website, :search_url, :detail_url,
                :format, :example,
                :has_year, :has_sector, :has_type, :category,
                :parser_enabled
            )
        """), {
            "state_code": row[0], "state_name": row[1], "commission_name": row[2], "abbr": row[3],
            "website": row[4], "search_url": row[5], "detail_url": row[6],
            "format": row[7], "example": row[8],
            "has_year": row[9], "has_sector": row[10], "has_type": row[11], "category": row[12],
            "parser_enabled": row[13]
        })

    db.commit()
    print(f"  Inserted {len(states_data)} state configurations")

    # Migration 006: Add new columns
    print("\nMigration 006: Adding docket_type and related columns...")

    # Check existing columns
    result = db.execute(text("PRAGMA table_info(known_dockets)")).fetchall()
    existing_cols = {row[1] for row in result}

    new_cols = [
        ("docket_type", "VARCHAR(50)"),
        ("company_code", "VARCHAR(20)"),
        ("raw_prefix", "VARCHAR(20)"),
        ("raw_suffix", "VARCHAR(20)"),
    ]

    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            db.execute(text(f"ALTER TABLE known_dockets ADD COLUMN {col_name} {col_type}"))
            print(f"  Added column: {col_name}")
        else:
            print(f"  Column already exists: {col_name}")

    # Check extracted_dockets columns
    result = db.execute(text("PRAGMA table_info(extracted_dockets)")).fetchall()
    existing_cols = {row[1] for row in result}

    extracted_cols = [
        ("parsed_year", "INTEGER"),
        ("parsed_utility_sector", "VARCHAR(50)"),
        ("parsed_docket_type", "VARCHAR(50)"),
        ("parsed_company_code", "VARCHAR(20)"),
    ]

    for col_name, col_type in extracted_cols:
        if col_name not in existing_cols:
            db.execute(text(f"ALTER TABLE extracted_dockets ADD COLUMN {col_name} {col_type}"))
            print(f"  Added column to extracted_dockets: {col_name}")
        else:
            print(f"  Column already exists in extracted_dockets: {col_name}")

    db.commit()
    print("  Migration 006 complete")

    # Verify
    print("\nVerifying state_psc_sources...")
    result = db.execute(text("SELECT COUNT(*) FROM state_psc_sources")).fetchone()
    print(f"  Total states in state_psc_sources: {result[0]}")

    result = db.execute(text("""
        SELECT state_code, docket_format, has_sector_in_id, has_type_in_id, parser_enabled
        FROM state_psc_sources
        WHERE parser_enabled = TRUE
        ORDER BY state_code
    """)).fetchall()
    print(f"\n  States with parser enabled ({len(result)}):")
    for row in result:
        print(f"    {row[0]}: {row[1]:20} sector={row[2]} type={row[3]}")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    db.rollback()
finally:
    db.close()

print("\n" + "=" * 60)
print("DONE")
print("=" * 60)
