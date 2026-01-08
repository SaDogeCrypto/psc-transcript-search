-- Florida Entity Linking Tables
-- Creates tables for linking hearings to dockets, utilities, and topics

-- Canonical utilities table
CREATE TABLE IF NOT EXISTS fl_utilities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) UNIQUE NOT NULL,
    aliases JSONB DEFAULT '[]',
    utility_type VARCHAR(50),
    sectors JSONB DEFAULT '[]',
    mention_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Canonical topics table
CREATE TABLE IF NOT EXISTS fl_topics (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    category VARCHAR(50),
    description TEXT,
    mention_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Hearing-to-Docket junction table (many-to-many)
CREATE TABLE IF NOT EXISTS fl_hearing_dockets (
    id SERIAL PRIMARY KEY,
    hearing_id INTEGER NOT NULL REFERENCES fl_hearings(id) ON DELETE CASCADE,
    docket_id INTEGER NOT NULL REFERENCES fl_dockets(id) ON DELETE CASCADE,
    mention_summary TEXT,
    timestamps_json JSONB,
    context_summary TEXT,
    confidence_score FLOAT,
    match_type VARCHAR(20),
    needs_review BOOLEAN DEFAULT FALSE,
    review_reason VARCHAR(255),
    review_notes TEXT,
    reviewed_at TIMESTAMP,
    reviewed_by VARCHAR(100),
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(hearing_id, docket_id)
);

-- Hearing-to-Utility junction table
CREATE TABLE IF NOT EXISTS fl_hearing_utilities (
    id SERIAL PRIMARY KEY,
    hearing_id INTEGER NOT NULL REFERENCES fl_hearings(id) ON DELETE CASCADE,
    utility_id INTEGER NOT NULL REFERENCES fl_utilities(id) ON DELETE CASCADE,
    role VARCHAR(50),
    context_summary TEXT,
    confidence_score FLOAT,
    match_type VARCHAR(20),
    confidence VARCHAR(20),
    needs_review BOOLEAN DEFAULT FALSE,
    review_reason VARCHAR(255),
    review_notes TEXT,
    reviewed_at TIMESTAMP,
    reviewed_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(hearing_id, utility_id)
);

-- Hearing-to-Topic junction table
CREATE TABLE IF NOT EXISTS fl_hearing_topics (
    id SERIAL PRIMARY KEY,
    hearing_id INTEGER NOT NULL REFERENCES fl_hearings(id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES fl_topics(id) ON DELETE CASCADE,
    relevance_score FLOAT,
    mention_count INTEGER DEFAULT 1,
    context_summary TEXT,
    sentiment VARCHAR(20),
    confidence_score FLOAT,
    match_type VARCHAR(20),
    confidence VARCHAR(20),
    needs_review BOOLEAN DEFAULT FALSE,
    review_reason VARCHAR(255),
    review_notes TEXT,
    reviewed_at TIMESTAMP,
    reviewed_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(hearing_id, topic_id)
);

-- Entity corrections for training data
CREATE TABLE IF NOT EXISTS fl_entity_corrections (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(20) NOT NULL,
    hearing_id INTEGER REFERENCES fl_hearings(id) ON DELETE SET NULL,
    original_text TEXT NOT NULL,
    original_entity_id INTEGER,
    corrected_text TEXT,
    correct_entity_id INTEGER,
    correction_type VARCHAR(20) NOT NULL,
    transcript_context TEXT,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_fl_hearing_dockets_hearing ON fl_hearing_dockets(hearing_id);
CREATE INDEX IF NOT EXISTS idx_fl_hearing_dockets_docket ON fl_hearing_dockets(docket_id);
CREATE INDEX IF NOT EXISTS idx_fl_hearing_dockets_review ON fl_hearing_dockets(needs_review) WHERE needs_review = TRUE;

CREATE INDEX IF NOT EXISTS idx_fl_hearing_utilities_hearing ON fl_hearing_utilities(hearing_id);
CREATE INDEX IF NOT EXISTS idx_fl_hearing_utilities_utility ON fl_hearing_utilities(utility_id);
CREATE INDEX IF NOT EXISTS idx_fl_hearing_utilities_review ON fl_hearing_utilities(needs_review) WHERE needs_review = TRUE;

CREATE INDEX IF NOT EXISTS idx_fl_hearing_topics_hearing ON fl_hearing_topics(hearing_id);
CREATE INDEX IF NOT EXISTS idx_fl_hearing_topics_topic ON fl_hearing_topics(topic_id);
CREATE INDEX IF NOT EXISTS idx_fl_hearing_topics_review ON fl_hearing_topics(needs_review) WHERE needs_review = TRUE;

CREATE INDEX IF NOT EXISTS idx_fl_utilities_normalized ON fl_utilities(normalized_name);
CREATE INDEX IF NOT EXISTS idx_fl_topics_slug ON fl_topics(slug);

-- Seed Florida utilities
INSERT INTO fl_utilities (name, normalized_name, utility_type, sectors, aliases) VALUES
    ('Florida Power & Light Company', 'florida power & light company', 'IOU', '["electric"]', '["FPL", "Florida Power and Light", "FP&L"]'),
    ('Duke Energy Florida', 'duke energy florida', 'IOU', '["electric"]', '["DEF", "Duke Florida", "Duke Energy"]'),
    ('Tampa Electric Company', 'tampa electric company', 'IOU', '["electric"]', '["TECO", "Tampa Electric"]'),
    ('Gulf Power Company', 'gulf power company', 'IOU', '["electric"]', '["Gulf Power"]'),
    ('Florida Public Utilities Company', 'florida public utilities company', 'IOU', '["electric", "gas"]', '["FPUC", "FPU"]'),
    ('Peoples Gas System', 'peoples gas system', 'IOU', '["gas"]', '["Peoples Gas", "PGS"]'),
    ('Florida City Gas', 'florida city gas', 'IOU', '["gas"]', '["FCG"]'),
    ('TECO Peoples Gas', 'teco peoples gas', 'IOU', '["gas"]', '["TPG"]'),
    ('JEA', 'jea', 'Municipal', '["electric", "water"]', '["Jacksonville Electric Authority"]'),
    ('Orlando Utilities Commission', 'orlando utilities commission', 'Municipal', '["electric", "water"]', '["OUC"]'),
    ('Gainesville Regional Utilities', 'gainesville regional utilities', 'Municipal', '["electric", "gas", "water"]', '["GRU"]'),
    ('Kissimmee Utility Authority', 'kissimmee utility authority', 'Municipal', '["electric"]', '["KUA"]'),
    ('Florida Keys Electric Cooperative', 'florida keys electric cooperative', 'Coop', '["electric"]', '["FKEC"]'),
    ('Clay Electric Cooperative', 'clay electric cooperative', 'Coop', '["electric"]', '["Clay Electric"]'),
    ('Suwannee Valley Electric Cooperative', 'suwannee valley electric cooperative', 'Coop', '["electric"]', '["SVEC"]')
ON CONFLICT (normalized_name) DO NOTHING;

-- Seed regulatory topics
INSERT INTO fl_topics (name, slug, category, description) VALUES
    ('Rate Case', 'rate-case', 'rates', 'Base rate proceedings to set utility rates'),
    ('Fuel Clause', 'fuel-clause', 'rates', 'Fuel cost recovery and adjustment proceedings'),
    ('Nuclear Cost Recovery', 'nuclear-cost-recovery', 'rates', 'Nuclear plant cost recovery clause'),
    ('Storm Cost Recovery', 'storm-cost-recovery', 'rates', 'Hurricane and storm damage cost recovery'),
    ('Depreciation', 'depreciation', 'rates', 'Depreciation studies and rates'),
    ('Return on Equity', 'return-on-equity', 'rates', 'Authorized return on equity proceedings'),
    ('Grid Modernization', 'grid-modernization', 'operations', 'Smart grid and infrastructure improvements'),
    ('Solar', 'solar', 'generation', 'Solar energy and net metering'),
    ('Battery Storage', 'battery-storage', 'generation', 'Energy storage systems'),
    ('Electric Vehicles', 'electric-vehicles', 'transportation', 'EV charging infrastructure'),
    ('Service Quality', 'service-quality', 'operations', 'Service reliability and quality standards'),
    ('Customer Complaints', 'customer-complaints', 'operations', 'Customer service issues'),
    ('Interconnection', 'interconnection', 'operations', 'Generator interconnection proceedings'),
    ('Territorial Disputes', 'territorial-disputes', 'policy', 'Service territory issues'),
    ('Conservation', 'conservation', 'policy', 'Demand side management and conservation'),
    ('Tariff', 'tariff', 'rates', 'Tariff filings and modifications'),
    ('Certificate', 'certificate', 'policy', 'Certificates of need and authorization'),
    ('Pipeline Safety', 'pipeline-safety', 'operations', 'Gas pipeline safety and compliance'),
    ('Water Quality', 'water-quality', 'operations', 'Water system quality standards'),
    ('Wastewater', 'wastewater', 'operations', 'Wastewater treatment systems')
ON CONFLICT (slug) DO NOTHING;

-- Grant permissions (adjust as needed for your setup)
-- GRANT ALL ON ALL TABLES IN SCHEMA public TO your_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO your_user;
