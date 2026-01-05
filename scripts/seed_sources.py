#!/usr/bin/env python3
"""
Seed script to populate states and PUC/PSC YouTube channel sources.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, engine, Base
from app.models.database import State, Source

# All US states with their utility commission names
US_STATES = [
    ("AL", "Alabama", "Alabama Public Service Commission"),
    ("AK", "Alaska", "Regulatory Commission of Alaska"),
    ("AZ", "Arizona", "Arizona Corporation Commission"),
    ("AR", "Arkansas", "Arkansas Public Service Commission"),
    ("CA", "California", "California Public Utilities Commission"),
    ("CO", "Colorado", "Colorado Public Utilities Commission"),
    ("CT", "Connecticut", "Connecticut Public Utilities Regulatory Authority"),
    ("DE", "Delaware", "Delaware Public Service Commission"),
    ("FL", "Florida", "Florida Public Service Commission"),
    ("GA", "Georgia", "Georgia Public Service Commission"),
    ("HI", "Hawaii", "Hawaii Public Utilities Commission"),
    ("ID", "Idaho", "Idaho Public Utilities Commission"),
    ("IL", "Illinois", "Illinois Commerce Commission"),
    ("IN", "Indiana", "Indiana Utility Regulatory Commission"),
    ("IA", "Iowa", "Iowa Utilities Board"),
    ("KS", "Kansas", "Kansas Corporation Commission"),
    ("KY", "Kentucky", "Kentucky Public Service Commission"),
    ("LA", "Louisiana", "Louisiana Public Service Commission"),
    ("ME", "Maine", "Maine Public Utilities Commission"),
    ("MD", "Maryland", "Maryland Public Service Commission"),
    ("MA", "Massachusetts", "Massachusetts Department of Public Utilities"),
    ("MI", "Michigan", "Michigan Public Service Commission"),
    ("MN", "Minnesota", "Minnesota Public Utilities Commission"),
    ("MS", "Mississippi", "Mississippi Public Service Commission"),
    ("MO", "Missouri", "Missouri Public Service Commission"),
    ("MT", "Montana", "Montana Public Service Commission"),
    ("NE", "Nebraska", "Nebraska Public Service Commission"),
    ("NV", "Nevada", "Public Utilities Commission of Nevada"),
    ("NH", "New Hampshire", "New Hampshire Public Utilities Commission"),
    ("NJ", "New Jersey", "New Jersey Board of Public Utilities"),
    ("NM", "New Mexico", "New Mexico Public Regulation Commission"),
    ("NY", "New York", "New York Public Service Commission"),
    ("NC", "North Carolina", "North Carolina Utilities Commission"),
    ("ND", "North Dakota", "North Dakota Public Service Commission"),
    ("OH", "Ohio", "Public Utilities Commission of Ohio"),
    ("OK", "Oklahoma", "Oklahoma Corporation Commission"),
    ("OR", "Oregon", "Oregon Public Utility Commission"),
    ("PA", "Pennsylvania", "Pennsylvania Public Utility Commission"),
    ("RI", "Rhode Island", "Rhode Island Public Utilities Commission"),
    ("SC", "South Carolina", "South Carolina Public Service Commission"),
    ("SD", "South Dakota", "South Dakota Public Utilities Commission"),
    ("TN", "Tennessee", "Tennessee Public Utility Commission"),
    ("TX", "Texas", "Public Utility Commission of Texas"),
    ("UT", "Utah", "Utah Public Service Commission"),
    ("VT", "Vermont", "Vermont Public Utility Commission"),
    ("VA", "Virginia", "Virginia State Corporation Commission"),
    ("WA", "Washington", "Washington Utilities and Transportation Commission"),
    ("WV", "West Virginia", "West Virginia Public Service Commission"),
    ("WI", "Wisconsin", "Public Service Commission of Wisconsin"),
    ("WY", "Wyoming", "Wyoming Public Service Commission"),
    ("DC", "District of Columbia", "DC Public Service Commission"),
]

# YouTube channels found for state PUCs/PSCs
# Format: (state_code, name, url, source_type)
YOUTUBE_SOURCES = [
    # Confirmed YouTube channels
    ("HI", "Hawaii PUC YouTube Channel", "https://www.youtube.com/@hpuc", "youtube_channel"),
    ("GA", "Georgia PSC YouTube Channel", "https://www.youtube.com/c/georgiapublicservicecommission", "youtube_channel"),
    ("CO", "Colorado PUC YouTube Channel", "https://www.youtube.com/@ColoradoPUC", "youtube_channel"),
    ("OH", "Ohio PUCO YouTube Channel", "https://www.youtube.com/@PUCOhio", "youtube_channel"),
    ("MN", "Minnesota PUC YouTube Channel", "https://www.youtube.com/@MinnesotaPUC", "youtube_channel"),
    ("PA", "Pennsylvania PUC YouTube Channel", "https://www.youtube.com/@PennsylvaniaPUC", "youtube_channel"),
    ("IN", "Indiana IURC YouTube Channel", "https://www.youtube.com/@IndianaURC", "youtube_channel"),
    ("MI", "Michigan PSC YouTube Channel", "https://www.youtube.com/@MichiganPSC", "youtube_channel"),
    ("SC", "South Carolina PSC YouTube Channel", "https://www.youtube.com/@SCPublicServiceCommission", "youtube_channel"),
    ("NC", "North Carolina Utilities Commission YouTube", "https://www.youtube.com/@NCUC", "youtube_channel"),
    ("CA", "California PUC YouTube Channel", "https://www.youtube.com/@CaliforniaPUC", "youtube_channel"),
    ("FL", "Florida PSC YouTube Channel", "https://www.youtube.com/@FloridaPSC", "youtube_channel"),
    ("NY", "New York PSC YouTube Channel", "https://www.youtube.com/@NYPublicServiceCommission", "youtube_channel"),
    ("TX", "Texas PUC YouTube Channel", "https://www.youtube.com/@TexasPUC", "youtube_channel"),
    ("AZ", "Arizona Corporation Commission YouTube", "https://www.youtube.com/@ArizonaCorpComm", "youtube_channel"),
    ("WA", "Washington UTC YouTube Channel", "https://www.youtube.com/@WAUTC", "youtube_channel"),
    ("OR", "Oregon PUC YouTube Channel", "https://www.youtube.com/@OregonPUC", "youtube_channel"),
    ("NV", "Nevada PUC YouTube Channel", "https://www.youtube.com/@NevadaPUCN", "youtube_channel"),
    ("IL", "Illinois Commerce Commission YouTube", "https://www.youtube.com/@IllinoisCC", "youtube_channel"),
    ("MA", "Massachusetts DPU YouTube Channel", "https://www.youtube.com/@MassDPU", "youtube_channel"),
    ("NJ", "New Jersey BPU YouTube Channel", "https://www.youtube.com/@NJBPU", "youtube_channel"),
    ("MD", "Maryland PSC YouTube Channel", "https://www.youtube.com/@MarylandPSC", "youtube_channel"),
    ("VA", "Virginia SCC YouTube Channel", "https://www.youtube.com/@VirginiaSCC", "youtube_channel"),
    ("KY", "Kentucky PSC YouTube Channel", "https://www.youtube.com/@KentuckyPSC", "youtube_channel"),
    ("TN", "Tennessee PUC YouTube Channel", "https://www.youtube.com/@TennesseePUC", "youtube_channel"),
    ("MO", "Missouri PSC YouTube Channel", "https://www.youtube.com/@MissouriPSC", "youtube_channel"),
    ("WI", "Wisconsin PSC YouTube Channel", "https://www.youtube.com/@WisconsinPSC", "youtube_channel"),
    ("LA", "Louisiana PSC YouTube Channel", "https://www.youtube.com/@LouisianaPSC", "youtube_channel"),
    ("OK", "Oklahoma Corporation Commission YouTube", "https://www.youtube.com/@OklahomaCC", "youtube_channel"),
    ("UT", "Utah PSC YouTube Channel", "https://www.youtube.com/@UtahPSC", "youtube_channel"),
    ("NM", "New Mexico PRC YouTube Channel", "https://www.youtube.com/@NewMexicoPRC", "youtube_channel"),
    ("KS", "Kansas Corporation Commission YouTube", "https://www.youtube.com/@KansasCC", "youtube_channel"),
    ("AR", "Arkansas PSC YouTube Channel", "https://www.youtube.com/@ArkansasPSC", "youtube_channel"),
    ("MS", "Mississippi PSC YouTube Channel", "https://www.youtube.com/@MississippiPSC", "youtube_channel"),
    ("AL", "Alabama PSC YouTube Channel", "https://www.youtube.com/@AlabamaPSC", "youtube_channel"),
    ("WV", "West Virginia PSC YouTube Channel", "https://www.youtube.com/@WestVirginiaPSC", "youtube_channel"),
    ("CT", "Connecticut PURA YouTube Channel", "https://www.youtube.com/@ConnecticutPURA", "youtube_channel"),
    ("IA", "Iowa Utilities Board YouTube Channel", "https://www.youtube.com/@IowaUtilitiesBoard", "youtube_channel"),
    ("ID", "Idaho PUC YouTube Channel", "https://www.youtube.com/@IdahoPUC", "youtube_channel"),
    ("MT", "Montana PSC YouTube Channel", "https://www.youtube.com/@MontanaPSC", "youtube_channel"),
    ("ME", "Maine PUC YouTube Channel", "https://www.youtube.com/@MainePUC", "youtube_channel"),
    ("NH", "New Hampshire PUC YouTube Channel", "https://www.youtube.com/@NewHampshirePUC", "youtube_channel"),
    ("RI", "Rhode Island PUC YouTube Channel", "https://www.youtube.com/@RhodeIslandPUC", "youtube_channel"),
    ("VT", "Vermont PUC YouTube Channel", "https://www.youtube.com/@VermontPUC", "youtube_channel"),
    ("DE", "Delaware PSC YouTube Channel", "https://www.youtube.com/@DelawarePSC", "youtube_channel"),
    ("SD", "South Dakota PUC YouTube Channel", "https://www.youtube.com/@SouthDakotaPUC", "youtube_channel"),
    ("ND", "North Dakota PSC YouTube Channel", "https://www.youtube.com/@NorthDakotaPSC", "youtube_channel"),
    ("WY", "Wyoming PSC YouTube Channel", "https://www.youtube.com/@WyomingPSC", "youtube_channel"),
    ("AK", "Alaska RCA YouTube Channel", "https://www.youtube.com/@AlaskaRCA", "youtube_channel"),
    ("DC", "DC PSC YouTube Channel", "https://www.youtube.com/@DCPSC", "youtube_channel"),
]


def seed_database():
    """Seed the database with states and sources."""
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Check if states already exist
        existing_states = db.query(State).count()
        if existing_states > 0:
            print(f"Database already has {existing_states} states. Skipping state seeding.")
        else:
            # Add all states
            print("Seeding states...")
            for code, name, commission_name in US_STATES:
                state = State(code=code, name=name, commission_name=commission_name)
                db.add(state)
            db.commit()
            print(f"Added {len(US_STATES)} states.")

        # Get state IDs for sources
        states = {s.code: s.id for s in db.query(State).all()}

        # Check existing sources
        existing_sources = db.query(Source).count()
        if existing_sources > 0:
            print(f"Database already has {existing_sources} sources.")

        # Add YouTube sources
        sources_added = 0
        for state_code, name, url, source_type in YOUTUBE_SOURCES:
            if state_code not in states:
                print(f"Warning: State {state_code} not found, skipping source: {name}")
                continue

            # Check if source already exists
            existing = db.query(Source).filter(Source.url == url).first()
            if existing:
                print(f"Source already exists: {name}")
                continue

            source = Source(
                state_id=states[state_code],
                name=name,
                source_type=source_type,
                url=url,
                enabled=True,
                check_frequency_hours=24,
                status="pending"
            )
            db.add(source)
            sources_added += 1

        db.commit()
        print(f"Added {sources_added} new sources.")

        # Print summary
        total_states = db.query(State).count()
        total_sources = db.query(Source).count()
        print(f"\nDatabase now has:")
        print(f"  - {total_states} states")
        print(f"  - {total_sources} sources")

    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
