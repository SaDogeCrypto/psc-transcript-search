"""
Seed data for Florida PSC entities.

Contains major utilities, intervenors, and commissioners for initial database seeding.
"""

FL_MAJOR_PARTIES = [
    # IOUs
    {
        "name": "Florida Power & Light Company",
        "short_name": "FPL",
        "party_type": "IOU",
        "parent_company": "NextEra Energy",
        "sectors": ["electric"]
    },
    {
        "name": "Duke Energy Florida",
        "short_name": "DEF",
        "party_type": "IOU",
        "parent_company": "Duke Energy",
        "sectors": ["electric"]
    },
    {
        "name": "Tampa Electric Company",
        "short_name": "TECO",
        "party_type": "IOU",
        "parent_company": "Emera",
        "sectors": ["electric"]
    },
    {
        "name": "Gulf Power Company",
        "short_name": "Gulf",
        "party_type": "IOU",
        "parent_company": "NextEra Energy",
        "sectors": ["electric"]
    },
    {
        "name": "Florida Public Utilities Company",
        "short_name": "FPUC",
        "party_type": "IOU",
        "sectors": ["electric", "gas"]
    },
    {
        "name": "Peoples Gas System",
        "short_name": "PGS",
        "party_type": "IOU",
        "parent_company": "Emera",
        "sectors": ["gas"]
    },

    # Consumer advocates
    {
        "name": "Office of Public Counsel",
        "short_name": "OPC",
        "party_type": "agency"
    },

    # Frequent intervenors
    {
        "name": "Florida Industrial Power Users Group",
        "short_name": "FIPUG",
        "party_type": "intervenor"
    },
    {
        "name": "Florida Retail Federation",
        "short_name": "FRF",
        "party_type": "intervenor"
    },
    {
        "name": "AARP",
        "short_name": "AARP",
        "party_type": "intervenor"
    },
    {
        "name": "Sierra Club",
        "short_name": "Sierra Club",
        "party_type": "intervenor"
    },
    {
        "name": "Southern Alliance for Clean Energy",
        "short_name": "SACE",
        "party_type": "intervenor"
    },
    {
        "name": "Vote Solar",
        "short_name": "Vote Solar",
        "party_type": "intervenor"
    },

    # Staff
    {
        "name": "Florida PSC Staff",
        "short_name": "Staff",
        "party_type": "staff"
    },
]

FL_COMMISSIONERS = [
    {
        "name": "Mike La Rosa",
        "title": "Chairman",
        "appointed_by": "Ron DeSantis",
        "active": True
    },
    {
        "name": "Art Graham",
        "title": "Commissioner",
        "appointed_by": "Charlie Crist",
        "active": True
    },
    {
        "name": "Gary Clark",
        "title": "Commissioner",
        "appointed_by": "Rick Scott",
        "active": True
    },
    {
        "name": "Mike Forrest",
        "title": "Commissioner",
        "appointed_by": "Ron DeSantis",
        "active": True
    },
    {
        "name": "Gabriella Passidomo",
        "title": "Commissioner",
        "appointed_by": "Ron DeSantis",
        "active": True
    },
]

# Document types taxonomy
FL_DOCUMENT_TYPES = [
    {"code": "PETITION", "name": "Petition", "category": "filing"},
    {"code": "TESTIMONY", "name": "Testimony", "category": "filing"},
    {"code": "EXHIBIT", "name": "Exhibit", "category": "filing"},
    {"code": "MOTION", "name": "Motion", "category": "filing"},
    {"code": "RESPONSE", "name": "Response", "category": "filing"},
    {"code": "BRIEF", "name": "Brief", "category": "filing"},
    {"code": "ORDER", "name": "Order", "category": "order"},
    {"code": "PAA", "name": "Proposed Agency Action", "category": "order"},
    {"code": "NOTICE", "name": "Notice", "category": "order"},
    {"code": "TRANSCRIPT", "name": "Transcript", "category": "transcript"},
    {"code": "DISCOVERY", "name": "Discovery", "category": "discovery"},
    {"code": "TARIFF", "name": "Tariff Filing", "category": "filing"},
]
