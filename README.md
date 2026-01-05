# PSC Hearing Transcript Search

A web application for searching AI-transcribed public utility commission (PSC/PUC) hearing recordings. The pilot focuses on Georgia PSC hearings related to Georgia Power.

## Overview

Transform hours of unsearchable YouTube video into a searchable transcript database with timestamps that link back to the source video.

### Target Content (Pilot)

- **Source:** Georgia Public Service Commission YouTube Channel
- **Dockets:** #56298 and #56310 (2029-2031 All-Source Capacity RFP)
- **Dates:** December 10-19, 2025
- **Duration:** ~10-20 hours of hearing video

## Architecture

```
YouTube Videos → yt-dlp → Audio Files → Whisper → Transcripts
                                                      ↓
React/Streamlit ← FastAPI ← PostgreSQL + pgvector ← Processing Pipeline
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- OpenAI API key
- yt-dlp installed (`pip install yt-dlp` or `brew install yt-dlp`)

### 1. Clone and Setup

```bash
git clone <repo>
cd psc-transcript-search

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment file and add your OpenAI API key
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### 2. Start Database

```bash
docker-compose up -d db
```

This starts PostgreSQL with the pgvector extension.

### 3. Initialize Database Schema

```bash
psql postgresql://postgres:postgres@localhost:5432/psc_transcripts -f init.sql
```

Or connect and run manually:

```bash
docker exec -it psc-transcript-search-db-1 psql -U postgres -d psc_transcripts -f /docker-entrypoint-initdb.d/init.sql
```

### 4. Run the Data Pipeline

```bash
# Step 1: Fetch video list from YouTube channel
python scripts/01_fetch_videos.py

# Step 2: Download audio from videos
python scripts/02_download_audio.py

# Step 3: Transcribe audio with Whisper (this takes time!)
python scripts/03_transcribe.py

# Step 4: Process segments (extract topics, generate embeddings)
python scripts/04_process_segments.py

# Step 5: Load into database
python scripts/05_load_database.py
```

### 5. Start the Application

**Backend:**

```bash
cd backend
python main.py
# API available at http://localhost:8000
```

**Frontend:**

```bash
cd frontend
streamlit run app.py
# UI available at http://localhost:8501
```

### Using Docker Compose (Full Stack)

```bash
docker-compose up --build
```

This starts all services:
- Database: PostgreSQL on port 5432
- Backend: FastAPI on port 8000
- Frontend: Streamlit on port 8501

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/api/search?q=...` | GET | Full-text search |
| `/api/search/semantic?q=...` | GET | Semantic search (uses embeddings) |
| `/api/search/topics?topic=...` | GET | Search by extracted topic |
| `/api/search/speaker?speaker=...` | GET | Search by speaker name/role |
| `/api/hearings` | GET | List all hearings |
| `/api/hearings/{id}` | GET | Get specific hearing |
| `/api/hearings/{id}/segments` | GET | Get segments for hearing |
| `/api/hearings/{id}/transcript` | GET | Get full transcript text |
| `/api/stats` | GET | Database statistics |

## Example Searches

Test the system with these queries:

1. `data center load forecast`
2. `solar capacity additions`
3. `rate impact residential customers`
4. `coal plant retirement`
5. `Commissioner Echols` (speaker search)
6. `9000 megawatts` (number search)
7. `McIntosh gas plant`
8. `PSC staff recommendation`

## Project Structure

```
psc-transcript-search/
├── README.md
├── requirements.txt
├── .env.example
├── docker-compose.yml
├── init.sql                    # Database schema
│
├── scripts/
│   ├── 01_fetch_videos.py      # Get video list from YouTube
│   ├── 02_download_audio.py    # Download audio with yt-dlp
│   ├── 03_transcribe.py        # Whisper transcription
│   ├── 04_process_segments.py  # LLM tagging, embeddings
│   └── 05_load_database.py     # Insert into PostgreSQL
│
├── backend/
│   ├── main.py                 # FastAPI app
│   ├── database.py             # DB connection
│   ├── models.py               # Pydantic models
│   ├── search.py               # Search logic
│   ├── Dockerfile
│   └── routers/
│       ├── hearings.py
│       └── search.py
│
├── frontend/
│   ├── app.py                  # Streamlit app
│   └── Dockerfile
│
└── data/
    ├── audio/                  # Downloaded audio files
    ├── transcripts/            # Raw Whisper output
    └── processed/              # Processed segments
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key for transcription and embeddings | Required |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:postgres@localhost:5432/psc_transcripts` |
| `USE_WHISPER_API` | Use OpenAI Whisper API instead of local | `false` |

### Whisper Model Selection

In `scripts/03_transcribe.py`, you can change the model:

```python
MODEL_SIZE = "medium"  # Options: tiny, base, small, medium, large-v3
```

- `medium`: Good balance of speed and accuracy
- `large-v3`: Best accuracy, but slower and requires more VRAM

## Success Criteria

The pilot is successful if:

1. **Transcription quality:** >90% accurate on regulatory terminology
2. **Search relevance:** Top 5 results are relevant for test queries
3. **User validation:** "I would pay for this"
4. **Performance:** Search returns results in <2 seconds

## Future Enhancements

1. **Semantic search** - Use embeddings for meaning-based search
2. **Speaker diarization** - Better "who said what" using AssemblyAI
3. **Alert system** - Notify users when new relevant content is indexed
4. **Multi-state expansion** - Add California, Texas, etc.
5. **Comparative search** - "How did GA handle X vs. how CA handled X"
6. **API access** - Let power users query programmatically

## Troubleshooting

### Database connection issues

```bash
# Check if PostgreSQL is running
docker ps

# View database logs
docker-compose logs db
```

### Whisper out of memory

Try a smaller model:

```python
MODEL_SIZE = "small"  # or "base" for very limited VRAM
```

### yt-dlp download failures

Update yt-dlp:

```bash
pip install --upgrade yt-dlp
```

## License

MIT
