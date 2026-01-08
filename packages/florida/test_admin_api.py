#!/usr/bin/env python3
"""
Local test script for Florida Admin API.
Run this before deploying to Azure to catch issues early.

Usage:
    export FL_DATABASE_URL='postgresql://...'
    python test_admin_api.py
"""

import os
import sys
import json

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fastapi.testclient import TestClient
from florida.api.app import app

client = TestClient(app)

def test_endpoint(path: str, expected_fields: list = None):
    """Test an endpoint and print results."""
    try:
        r = client.get(path)
        status = "✅" if r.status_code == 200 else "❌"
        print(f"{status} {path}: {r.status_code}")

        if r.status_code == 200:
            data = r.json()
            if expected_fields:
                missing = [f for f in expected_fields if f not in data]
                if missing:
                    print(f"   ⚠️  Missing fields: {missing}")
            return data
        else:
            print(f"   Error: {r.text[:100]}")
            return None
    except Exception as e:
        print(f"❌ {path}: {e}")
        return None

def main():
    print("=" * 60)
    print("Florida Admin API - Local Test")
    print("=" * 60)
    print()

    # Test pipeline status
    print("📊 Pipeline Status")
    data = test_endpoint('/admin/pipeline/status', ['stage_counts', 'hearings_processed'])
    if data:
        counts = data.get('stage_counts', {})
        total = sum(counts.values())
        print(f"   Buckets: {counts}")
        print(f"   Total: {total}")
    print()

    # Test stats
    print("📈 Admin Stats")
    data = test_endpoint('/admin/stats', ['total_hearings', 'total_segments', 'hearings_by_status'])
    if data:
        print(f"   Hearings: {data.get('total_hearings')}")
        print(f"   Segments: {data.get('total_segments')}")
        print(f"   By status: {data.get('hearings_by_status')}")
    print()

    # Test data quality
    print("🔍 Data Quality")
    data = test_endpoint('/admin/pipeline/data-quality', ['docket_confidence', 'docket_sources'])
    if data:
        print(f"   docket_confidence: {data.get('docket_confidence')}")
        print(f"   docket_sources: {data.get('docket_sources')}")
    print()

    # Test other endpoints
    print("🔧 Other Endpoints")
    test_endpoint('/admin/states')
    test_endpoint('/admin/sources')
    test_endpoint('/admin/hearings?page_size=5')
    test_endpoint('/admin/review/stats', ['total'])
    test_endpoint('/admin/review/hearings?limit=5', ['items', 'total'])
    test_endpoint('/admin/scraper/status', ['status'])
    test_endpoint('/admin/pipeline/docket-discovery/stats')
    test_endpoint('/admin/pipeline/docket-sources')
    print()

    # Verify counts match
    print("✓ Validation")
    pipeline = client.get('/admin/pipeline/status').json()
    stats = client.get('/admin/stats').json()

    pipeline_total = sum(pipeline['stage_counts'].values())
    stats_total = stats['total_hearings']

    if pipeline_total == stats_total:
        print(f"   ✅ Pipeline buckets ({pipeline_total}) match total hearings ({stats_total})")
    else:
        print(f"   ❌ MISMATCH: Pipeline buckets ({pipeline_total}) != total hearings ({stats_total})")

    print()
    print("=" * 60)
    print("Done!")

if __name__ == '__main__':
    main()
