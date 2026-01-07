-- Migration 005: Complete Entity Matching System
-- Topics, utilities, entity linking, and manual review workflow

-- ============================================================================
-- TOPICS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS topics (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    slug VARCHAR(100) NOT NULL UNIQUE,
    category VARCHAR(50),  -- 'policy', 'technical', 'regulatory', 'consumer', 'uncategorized'
    description TEXT,
    mention_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_topics_slug ON topics(slug);
CREATE INDEX IF NOT EXISTS idx_topics_category ON topics(category);

-- Seed predefined topic taxonomy
INSERT INTO topics (name, slug, category) VALUES
-- Policy topics
('Grid Reliability', 'grid-reliability', 'policy'),
('Renewable Energy', 'renewable-energy', 'policy'),
('Rate Design', 'rate-design', 'policy'),
('Energy Efficiency', 'energy-efficiency', 'policy'),
('Demand Response', 'demand-response', 'policy'),
('Net Metering', 'net-metering', 'policy'),
('Carbon Reduction', 'carbon-reduction', 'policy'),
('Electrification', 'electrification', 'policy'),
-- Technical topics
('Solar Interconnection', 'solar-interconnection', 'technical'),
('Battery Storage', 'battery-storage', 'technical'),
('Grid Modernization', 'grid-modernization', 'technical'),
('Smart Meters', 'smart-meters', 'technical'),
('EV Charging', 'ev-charging', 'technical'),
('Transmission Planning', 'transmission-planning', 'technical'),
('Cybersecurity', 'cybersecurity', 'technical'),
-- Regulatory topics
('Rate Case', 'rate-case', 'regulatory'),
('Integrated Resource Plan', 'integrated-resource-plan', 'regulatory'),
('Certificate of Need', 'certificate-of-need', 'regulatory'),
('Fuel Cost Recovery', 'fuel-cost-recovery', 'regulatory'),
('Storm Cost Recovery', 'storm-cost-recovery', 'regulatory'),
('Affiliate Transactions', 'affiliate-transactions', 'regulatory'),
-- Consumer topics
('Low Income Programs', 'low-income-programs', 'consumer'),
('Bill Assistance', 'bill-assistance', 'consumer'),
('Disconnection Policy', 'disconnection-policy', 'consumer'),
('Consumer Complaints', 'consumer-complaints', 'consumer')
ON CONFLICT (slug) DO NOTHING;


-- ============================================================================
-- HEARING_TOPICS JUNCTION TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS hearing_topics (
    id SERIAL PRIMARY KEY,
    hearing_id INTEGER REFERENCES hearings(id) ON DELETE CASCADE,
    topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
    relevance_score FLOAT,  -- 0-1, how central to hearing
    mention_count INTEGER DEFAULT 1,
    context_summary TEXT,
    sentiment VARCHAR(20),  -- 'positive', 'negative', 'neutral', 'mixed'
    confidence VARCHAR(20) DEFAULT 'auto',  -- 'auto', 'verified', 'manual'
    needs_review BOOLEAN DEFAULT FALSE,
    review_notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(hearing_id, topic_id)
);

CREATE INDEX IF NOT EXISTS idx_hearing_topics_hearing ON hearing_topics(hearing_id);
CREATE INDEX IF NOT EXISTS idx_hearing_topics_topic ON hearing_topics(topic_id);
CREATE INDEX IF NOT EXISTS idx_hearing_topics_needs_review ON hearing_topics(needs_review) WHERE needs_review = TRUE;


-- ============================================================================
-- UTILITIES TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS utilities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    normalized_name VARCHAR(200) NOT NULL UNIQUE,
    aliases JSONB DEFAULT '[]',
    parent_company VARCHAR(200),
    utility_type VARCHAR(50),  -- 'IOU', 'cooperative', 'municipal'
    sectors JSONB DEFAULT '[]',  -- ['electric', 'gas']
    states JSONB DEFAULT '[]',  -- ['FL', 'GA']
    website VARCHAR(500),
    mention_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_utilities_normalized ON utilities(normalized_name);
CREATE INDEX IF NOT EXISTS idx_utilities_name_search ON utilities USING GIN(to_tsvector('english', name));

-- Seed major utilities
INSERT INTO utilities (name, normalized_name, aliases, utility_type, sectors, states) VALUES
('Florida Power & Light', 'florida-power-light', '["FPL", "Florida Power and Light", "FP&L"]', 'IOU', '["electric"]', '["FL"]'),
('Duke Energy Florida', 'duke-energy-florida', '["Duke Florida", "DEF"]', 'IOU', '["electric"]', '["FL"]'),
('Tampa Electric', 'tampa-electric', '["TECO", "Tampa Electric Company"]', 'IOU', '["electric"]', '["FL"]'),
('Georgia Power', 'georgia-power', '["GPC", "Georgia Power Company"]', 'IOU', '["electric"]', '["GA"]'),
('Southern Company Gas', 'southern-company-gas', '["SCG", "Atlanta Gas Light"]', 'IOU', '["gas"]', '["GA"]'),
('Oncor', 'oncor', '["Oncor Electric"]', 'IOU', '["electric"]', '["TX"]'),
('CenterPoint Energy', 'centerpoint-energy', '["CenterPoint", "CNP"]', 'IOU', '["electric", "gas"]', '["TX"]'),
('Pacific Gas & Electric', 'pacific-gas-electric', '["PG&E", "PGE"]', 'IOU', '["electric", "gas"]', '["CA"]'),
('Southern California Edison', 'southern-california-edison', '["SCE", "Edison"]', 'IOU', '["electric"]', '["CA"]'),
('Ohio Edison', 'ohio-edison', '["FirstEnergy Ohio"]', 'IOU', '["electric"]', '["OH"]'),
('Duke Energy Ohio', 'duke-energy-ohio', '["Duke Ohio"]', 'IOU', '["electric", "gas"]', '["OH"]'),
('Office of Public Counsel', 'office-public-counsel', '["OPC", "Public Counsel"]', 'regulatory', '[]', '["FL"]')
ON CONFLICT (normalized_name) DO NOTHING;


-- ============================================================================
-- HEARING_UTILITIES JUNCTION TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS hearing_utilities (
    id SERIAL PRIMARY KEY,
    hearing_id INTEGER REFERENCES hearings(id) ON DELETE CASCADE,
    utility_id INTEGER REFERENCES utilities(id) ON DELETE CASCADE,
    role VARCHAR(50),  -- 'applicant', 'intervenor', 'subject'
    context_summary TEXT,
    confidence VARCHAR(20) DEFAULT 'auto',
    needs_review BOOLEAN DEFAULT FALSE,
    review_notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(hearing_id, utility_id)
);

CREATE INDEX IF NOT EXISTS idx_hearing_utilities_hearing ON hearing_utilities(hearing_id);
CREATE INDEX IF NOT EXISTS idx_hearing_utilities_utility ON hearing_utilities(utility_id);
CREATE INDEX IF NOT EXISTS idx_hearing_utilities_needs_review ON hearing_utilities(needs_review) WHERE needs_review = TRUE;


-- ============================================================================
-- UPDATE HEARINGS TABLE
-- ============================================================================

ALTER TABLE hearings ADD COLUMN IF NOT EXISTS sector VARCHAR(20);
ALTER TABLE hearings ADD COLUMN IF NOT EXISTS primary_utility_id INTEGER REFERENCES utilities(id);
ALTER TABLE hearings ADD COLUMN IF NOT EXISTS has_docket_references BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_hearings_sector ON hearings(sector);
CREATE INDEX IF NOT EXISTS idx_hearings_primary_utility ON hearings(primary_utility_id);


-- ============================================================================
-- UPDATE DOCKETS TABLE FOR REVIEW WORKFLOW
-- ============================================================================

ALTER TABLE dockets ADD COLUMN IF NOT EXISTS review_status VARCHAR(20) DEFAULT 'pending';
ALTER TABLE dockets ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR(100);
ALTER TABLE dockets ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP;
ALTER TABLE dockets ADD COLUMN IF NOT EXISTS review_notes TEXT;
ALTER TABLE dockets ADD COLUMN IF NOT EXISTS original_extracted TEXT;

CREATE INDEX IF NOT EXISTS idx_dockets_review_status ON dockets(review_status);

-- Add needs_review to hearing_dockets
ALTER TABLE hearing_dockets ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT FALSE;
ALTER TABLE hearing_dockets ADD COLUMN IF NOT EXISTS review_notes TEXT;
ALTER TABLE hearing_dockets ADD COLUMN IF NOT EXISTS context_summary TEXT;

CREATE INDEX IF NOT EXISTS idx_hearing_dockets_needs_review ON hearing_dockets(needs_review) WHERE needs_review = TRUE;


-- ============================================================================
-- ENTITY CORRECTIONS TABLE (for training/improvement)
-- ============================================================================

CREATE TABLE IF NOT EXISTS entity_corrections (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(20) NOT NULL,  -- 'docket', 'topic', 'utility'
    hearing_id INTEGER REFERENCES hearings(id),

    -- What was extracted vs corrected
    original_text TEXT NOT NULL,
    original_entity_id INTEGER,
    corrected_text TEXT,
    correct_entity_id INTEGER,

    correction_type VARCHAR(50),  -- 'typo', 'wrong_entity', 'merge', 'split', 'invalid', 'new'
    transcript_context TEXT,

    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entity_corrections_type ON entity_corrections(entity_type);
CREATE INDEX IF NOT EXISTS idx_entity_corrections_hearing ON entity_corrections(hearing_id);


-- ============================================================================
-- UNIFIED WATCHLIST (supports all entity types)
-- ============================================================================

-- Drop old user_watchlist if it exists with different schema
DROP TABLE IF EXISTS user_watchlist CASCADE;

CREATE TABLE user_watchlist (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,

    -- Polymorphic: one of these will be set
    entity_type VARCHAR(20) NOT NULL,  -- 'docket', 'topic', 'sector', 'utility', 'state'
    docket_id INTEGER REFERENCES dockets(id) ON DELETE CASCADE,
    topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
    utility_id INTEGER REFERENCES utilities(id) ON DELETE CASCADE,
    sector VARCHAR(20),  -- 'electric', 'gas', 'water', 'telecom'
    state_code VARCHAR(2),

    -- Notification preferences
    notify_on_mention BOOLEAN DEFAULT TRUE,
    notify_frequency VARCHAR(20) DEFAULT 'immediate',  -- 'immediate', 'daily', 'weekly'

    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT valid_entity CHECK (
        (entity_type = 'docket' AND docket_id IS NOT NULL) OR
        (entity_type = 'topic' AND topic_id IS NOT NULL) OR
        (entity_type = 'utility' AND utility_id IS NOT NULL) OR
        (entity_type = 'sector' AND sector IS NOT NULL) OR
        (entity_type = 'state' AND state_code IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_watchlist_user ON user_watchlist(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_entity_type ON user_watchlist(entity_type);
CREATE INDEX IF NOT EXISTS idx_watchlist_docket ON user_watchlist(docket_id) WHERE docket_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_watchlist_topic ON user_watchlist(topic_id) WHERE topic_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_watchlist_utility ON user_watchlist(utility_id) WHERE utility_id IS NOT NULL;
