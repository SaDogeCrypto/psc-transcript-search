"""
Streamlit frontend for PSC Transcript Search.
"""

import os
import streamlit as st
import requests

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="PSC Transcript Search",
    page_icon="",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .result-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        border-left: 4px solid #0066cc;
    }
    .speaker-badge {
        background-color: #e9ecef;
        padding: 0.2rem 0.5rem;
        border-radius: 0.25rem;
        font-size: 0.875rem;
    }
    .timestamp {
        font-family: monospace;
        color: #6c757d;
    }
    .quote-text {
        font-style: italic;
        color: #333;
        line-height: 1.6;
    }
</style>
""", unsafe_allow_html=True)

st.title("Georgia PSC Hearing Transcript Search")
st.markdown("Search through AI-transcribed public utility commission hearings")

# Tabs for different views
tab1, tab2, tab3, tab4 = st.tabs(["Search", "Browse Hearings", "Insights", "Statistics"])

with tab1:
    # Search options
    col1, col2 = st.columns([3, 1])

    with col1:
        query = st.text_input(
            "Search transcripts",
            placeholder="e.g., data center load forecast, solar capacity, rate increase...",
            key="search_query"
        )

    with col2:
        search_type = st.selectbox(
            "Search type",
            ["Full-text", "Semantic"],
            key="search_type"
        )

    if query:
        with st.spinner("Searching..."):
            try:
                if search_type == "Full-text":
                    response = requests.get(
                        f"{API_URL}/api/search",
                        params={"q": query, "limit": 50},
                        timeout=30
                    )
                else:
                    response = requests.get(
                        f"{API_URL}/api/search/semantic",
                        params={"q": query, "limit": 50},
                        timeout=30
                    )

                if response.status_code == 200:
                    data = response.json()
                    results = data["results"]

                    st.markdown(f"**Found {len(results)} results for:** _{query}_")
                    st.divider()

                    for result in results:
                        with st.container():
                            col1, col2 = st.columns([4, 1])

                            with col1:
                                # Speaker badge
                                speaker_info = ""
                                if result.get("speaker"):
                                    speaker_info = f"**{result['speaker']}**"
                                elif result.get("speaker_role"):
                                    speaker_info = f"_{result['speaker_role']}_"

                                if speaker_info:
                                    st.markdown(speaker_info)

                                st.markdown(f'"{result["text"]}"')
                                st.caption(f"From: {result['hearing_title']}")

                            with col2:
                                # Timestamp and link
                                minutes = int(result["start_time"] // 60)
                                seconds = int(result["start_time"] % 60)
                                timestamp = f"{minutes}:{seconds:02d}"

                                st.markdown(f"**{timestamp}**")
                                st.link_button(
                                    "Watch",
                                    result["youtube_timestamp_url"],
                                    use_container_width=True
                                )

                            st.divider()
                else:
                    st.error(f"Search failed with status {response.status_code}")
            except requests.exceptions.ConnectionError:
                st.error("Could not connect to the API. Make sure the backend is running.")
            except Exception as e:
                st.error(f"Search failed: {str(e)}")

with tab2:
    st.header("Indexed Hearings")

    # Check if we're viewing a transcript
    if "selected_hearing" in st.session_state and st.session_state.selected_hearing:
        hearing_id = st.session_state.selected_hearing

        # Back button
        if st.button("< Back to Hearings List"):
            st.session_state.selected_hearing = None
            st.rerun()

        try:
            # Get hearing info
            hearing_resp = requests.get(f"{API_URL}/api/hearings/{hearing_id}", timeout=10)
            segments_resp = requests.get(f"{API_URL}/api/hearings/{hearing_id}/segments?limit=500", timeout=30)

            if hearing_resp.status_code == 200 and segments_resp.status_code == 200:
                hearing = hearing_resp.json()["hearing"]
                segments = segments_resp.json()["segments"]

                st.subheader(hearing["title"])

                col1, col2 = st.columns([3, 1])
                with col1:
                    if hearing.get("duration_seconds"):
                        duration_min = hearing["duration_seconds"] // 60
                        st.write(f"**Duration:** {duration_min} minutes | **Segments:** {len(segments)}")
                with col2:
                    st.link_button("Watch on YouTube", hearing.get("youtube_url", "#"))

                st.divider()

                # Display transcript segments
                for seg in segments:
                    minutes = int(seg["start_time"] // 60)
                    seconds = int(seg["start_time"] % 60)
                    timestamp = f"{minutes}:{seconds:02d}"

                    col1, col2 = st.columns([6, 1])
                    with col1:
                        speaker = seg.get("speaker") or seg.get("speaker_role") or ""
                        if speaker and speaker != "Unknown":
                            st.markdown(f"**[{timestamp}] {speaker}:** {seg['text']}")
                        else:
                            st.markdown(f"**[{timestamp}]** {seg['text']}")
                    with col2:
                        youtube_id = seg.get("youtube_id", hearing.get("youtube_id", ""))
                        start_sec = int(seg["start_time"])
                        st.markdown(f"[Play](https://www.youtube.com/watch?v={youtube_id}&t={start_sec}s)")
            else:
                st.error("Could not load transcript")
        except Exception as e:
            st.error(f"Error loading transcript: {str(e)}")
    else:
        # Show hearings list
        try:
            response = requests.get(f"{API_URL}/api/hearings", timeout=10)
            if response.status_code == 200:
                hearings = response.json()["hearings"]

                if not hearings:
                    st.info("No hearings have been indexed yet. Run the data pipeline scripts to add content.")
                else:
                    for hearing in hearings:
                        with st.expander(f"{hearing['title']} ({hearing.get('segment_count', 0)} segments)"):
                            col1, col2 = st.columns([3, 1])

                            with col1:
                                if hearing.get("hearing_date"):
                                    st.write(f"**Date:** {hearing['hearing_date']}")
                                if hearing.get("duration_seconds"):
                                    duration_min = hearing["duration_seconds"] // 60
                                    st.write(f"**Duration:** {duration_min} minutes")
                                if hearing.get("description"):
                                    st.write(f"**Description:** {hearing['description'][:200]}...")

                            with col2:
                                st.link_button(
                                    "Watch on YouTube",
                                    hearing.get("youtube_url", "#"),
                                    use_container_width=True
                                )

                                if hearing.get("segment_count", 0) > 0:
                                    if st.button("View Transcript", key=f"transcript_{hearing['id']}"):
                                        st.session_state.selected_hearing = hearing["id"]
                                        st.rerun()

            else:
                st.error("Could not load hearings")
        except requests.exceptions.ConnectionError:
            st.warning("Could not connect to the API. Make sure the backend is running on port 8000.")
        except Exception as e:
            st.error(f"Error loading hearings: {str(e)}")

with tab3:
    st.header("AI Insights")
    st.markdown("LLM-generated analysis of hearing content, key moments, and potential outcomes")

    # Check if viewing specific insight
    if "selected_insight" in st.session_state and st.session_state.selected_insight:
        hearing_id = st.session_state.selected_insight

        if st.button("< Back to Insights List"):
            st.session_state.selected_insight = None
            st.rerun()

        try:
            # Get full insights
            resp = requests.get(f"{API_URL}/api/insights/{hearing_id}", timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                hi = data.get("hearing_insights", {})

                # Header with confidence score
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.subheader(f"Hearing: {hearing_id}")
                with col2:
                    confidence = hi.get("confidence_score", 0)
                    if confidence >= 0.8:
                        st.success(f"Confidence: {confidence:.0%}")
                    elif confidence >= 0.6:
                        st.warning(f"Confidence: {confidence:.0%}")
                    else:
                        st.error(f"Confidence: {confidence:.0%}")

                # One-sentence summary
                st.info(hi.get("one_sentence_summary", "No summary available"))

                # Commissioner mood
                mood = hi.get("commissioner_mood", "")
                if mood:
                    st.markdown(f"**Commissioner Mood:** {mood}")

                st.divider()

                # Executive Summary
                st.subheader("Executive Summary")
                st.write(hi.get("executive_summary", "No executive summary available"))

                # Key Takeaways
                st.subheader("Key Takeaways")
                takeaways = hi.get("key_takeaways", [])
                if takeaways:
                    for i, takeaway in enumerate(takeaways, 1):
                        st.markdown(f"{i}. {takeaway}")
                else:
                    st.write("No key takeaways identified")

                st.divider()

                # Central Dispute
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("Central Dispute")
                    st.write(hi.get("central_dispute", "Not identified"))

                    st.markdown("**Utility Position:**")
                    st.write(hi.get("utility_position", "Not identified"))

                with col2:
                    st.subheader("Opposition")
                    st.write(hi.get("opposition_position", "Not identified"))

                st.divider()

                # Potential Outcomes
                st.subheader("Potential Outcomes")
                outcomes = hi.get("potential_outcomes", [])
                if outcomes:
                    for outcome in outcomes:
                        with st.expander(f"{outcome.get('outcome', 'Unknown')} - {outcome.get('likelihood', 'Unknown')} likelihood"):
                            st.write(f"**Reasoning:** {outcome.get('reasoning', 'N/A')}")
                else:
                    st.write("No outcomes analysis available")

                # Vulnerabilities & Commitments
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("Utility Vulnerabilities")
                    vulnerabilities = hi.get("utility_vulnerabilities", [])
                    if vulnerabilities:
                        for v in vulnerabilities:
                            st.markdown(f"- {v}")
                    else:
                        st.write("None identified")

                with col2:
                    st.subheader("Utility Commitments")
                    commitments = hi.get("utility_commitments", [])
                    if commitments:
                        for c in commitments:
                            st.markdown(f"- {c}")
                    else:
                        st.write("None identified")

                st.divider()

                # Notable Segments
                st.subheader("Notable Segments")
                notable = [s for s in data.get("segment_insights", []) if s.get("is_notable")]

                if notable:
                    st.write(f"Found {len(notable)} segments flagged for review")

                    for seg in notable:
                        with st.expander(f"[{seg.get('start_time', 0):.0f}s] {seg.get('notable_reason', 'Notable moment')}"):
                            st.markdown(f'> "{seg.get("text", "")}"')

                            col1, col2, col3 = st.columns(3)
                            with col1:
                                speaker = seg.get("speaker_name") or seg.get("speaker_role", "Unknown")
                                st.write(f"**Speaker:** {speaker}")
                            with col2:
                                st.write(f"**Tone:** {seg.get('tone', 'neutral')}")
                            with col3:
                                st.write(f"**Topics:** {', '.join(seg.get('topics', []))}")

                            # Link to YouTube timestamp
                            if "youtube_id" in data:
                                start_sec = int(seg.get("start_time", 0))
                                yt_url = f"https://www.youtube.com/watch?v={data['youtube_id']}&t={start_sec}s"
                                st.markdown(f"[Watch on YouTube]({yt_url})")
                else:
                    st.write("No notable segments flagged")

            elif resp.status_code == 404:
                st.warning(f"No insights found for hearing {hearing_id}")
            else:
                st.error(f"Error loading insights: {resp.status_code}")

        except requests.exceptions.ConnectionError:
            st.error("Could not connect to the API")
        except Exception as e:
            st.error(f"Error: {str(e)}")

    else:
        # List all available insights
        try:
            response = requests.get(f"{API_URL}/api/insights", timeout=10)

            if response.status_code == 200:
                data = response.json()
                insights = data.get("insights", [])

                if not insights:
                    st.info("No AI insights have been generated yet. Run the insight extraction script on your transcripts.")
                else:
                    st.write(f"**{len(insights)} hearings analyzed**")

                    for insight in insights:
                        with st.expander(f"{insight.get('hearing_id', 'Unknown')} - {insight.get('notable_segments', 0)} notable segments"):
                            st.write(insight.get("one_sentence_summary", "No summary"))

                            col1, col2, col3 = st.columns(3)
                            with col1:
                                confidence = insight.get("confidence_score", 0)
                                st.metric("Confidence", f"{confidence:.0%}")
                            with col2:
                                st.metric("Notable Segments", insight.get("notable_segments", 0))
                            with col3:
                                mood = insight.get("commissioner_mood", "Unknown")
                                st.write(f"**Mood:** {mood[:30]}...")

                            if st.button("View Full Analysis", key=f"insight_{insight.get('hearing_id')}"):
                                st.session_state.selected_insight = insight.get("hearing_id")
                                st.rerun()
            else:
                st.error("Could not load insights")

        except requests.exceptions.ConnectionError:
            st.warning("Could not connect to the API. Make sure the backend is running.")
        except Exception as e:
            st.error(f"Error: {str(e)}")

with tab4:
    st.header("Database Statistics")

    try:
        response = requests.get(f"{API_URL}/api/stats", timeout=10)
        if response.status_code == 200:
            stats = response.json()

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Total Hearings", stats.get("hearings", 0))

            with col2:
                st.metric("Total Segments", stats.get("segments", 0))

            with col3:
                st.metric("Total Hours", f"{stats.get('total_hours', 0):.1f}")
        else:
            st.warning("Could not load statistics")
    except requests.exceptions.ConnectionError:
        st.info("Statistics will appear once the backend is running and data is loaded.")
    except Exception as e:
        st.error(f"Error loading statistics: {str(e)}")

# Sidebar with info
with st.sidebar:
    st.header("About")
    st.markdown("""
    This tool provides searchable transcripts of Georgia Public Service Commission
    hearings related to Georgia Power and electric utility regulation.

    **Currently indexed:**
    - December 2025 Capacity Decision
    - Docket #56298 / #56310

    **How it works:**
    1. Videos are downloaded from the official PSC YouTube channel
    2. Audio is transcribed using OpenAI Whisper
    3. Transcripts are indexed for full-text and semantic search
    4. Results link directly to the YouTube timestamp
    """)

    st.divider()

    st.header("Example Searches")
    example_queries = [
        "data center load forecast",
        "solar capacity additions",
        "rate impact residential",
        "coal plant retirement",
        "renewable energy",
        "capacity planning"
    ]

    for q in example_queries:
        if st.button(q, key=f"example_{q}"):
            st.session_state.search_query = q
            st.rerun()

    st.divider()

    st.header("API Status")
    try:
        response = requests.get(f"{API_URL}/", timeout=5)
        if response.status_code == 200:
            st.success("Backend: Connected")
        else:
            st.error("Backend: Error")
    except:
        st.error("Backend: Not connected")
