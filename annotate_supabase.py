import streamlit as st
import pandas as pd
import psycopg2
import bcrypt
import datetime
import os
from PIL import Image

# PostgreSQL Configuration
PG_CONFIG = {
    "dbname": st.secrets["dbname"],
    "user": st.secrets["user"],
    "password": st.secrets["password"],
    "host": st.secrets["host"],
    "port": st.secrets["port"]

}

# DB Connection

def get_db_connection():
    return psycopg2.connect(**PG_CONFIG)

# Log login time
def log_login_time(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO login_log (user_id, login_time) VALUES (%s, %s)", (user_id, datetime.datetime.now()))
    conn.commit()
    cur.close()
    conn.close()

# Get next unannotated image
def get_next_image(user_id):
    conn = get_db_connection()
    cur = conn.cursor()

    # Step 1: Select the next available image not annotated by the user, and not locked by others
    cur.execute("""
        SELECT i.image_name, i.tweet_text, i.llm_reasoning
        FROM input_data i
        WHERE i.image_name NOT IN (
            SELECT image_name FROM annotated 
        )
        AND (i.locked_by IS NULL OR i.lock_time < NOW() - INTERVAL '10 minutes')
        ORDER BY i.image_name
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    """, (user_id,))

    row = cur.fetchone()

    # Step 2: If found, lock the row by updating locked_by and lock_time
    if row:
        image_name = row[0]
        cur.execute("""
            UPDATE input_data
            SET locked_by = %s, lock_time = NOW()
            WHERE image_name = %s
        """, (user_id, image_name))
        conn.commit()

    cur.close()
    conn.close()
    return row


# Save annotation
def save_annotation(user_id, image_name, evidence, reasoning, naturalness, accept_status, annotator_comment):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM annotated WHERE user_id = %s AND image_name = %s", (user_id, image_name))
    cur.execute("""
        INSERT INTO annotated (user_id, image_name, evidence_recognition, reasoning_chain, text_naturalness, accept_status, annotator_comment)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (user_id, image_name, evidence, reasoning, naturalness, accept_status, annotator_comment))
    cur.execute("""
        UPDATE input_data
        SET locked_by = NULL, lock_time = NULL
        WHERE image_name = %s
    """, (image_name,))
    conn.commit()
    cur.close()
    conn.close()

# Get progress
def get_progress(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM input_data")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM annotated")
    done = cur.fetchone()[0]
    cur.close()
    conn.close()
    return done, total
# Remove Lock from images    
def release_locks(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE input_data
        SET locked_by = NULL, lock_time = NULL
        WHERE locked_by = %s
    """, (user_id,))
    conn.commit()
    cur.close()
    conn.close()
# Login UI
def login_ui():
    st.title("🔐 Login to Annotation Tool")
    user_id = st.text_input("User ID")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT password, COALESCE(role, 'annotator') FROM user_data WHERE user_id = %s", (user_id,))
        result = cur.fetchone()
        cur.close()
        conn.close()
        if result:
            stored_password, role = result
            if bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8')):
                if role != 'annotator':
                    st.error("🚫 Access denied: This account does not have annotator privileges.")
                else:
                    st.session_state.logged_in = True
                    st.session_state.user_id = user_id
                    log_login_time(user_id)
                    st.rerun()
            else:
                st.error("❌ Incorrect password.")
        else:
            st.error("❌ User ID not found.")
        st.stop()

# Review Mode
def review_mode():
    st.success("✅ All annotations done!")

# Main app logic
def main():
    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        login_ui()
        return  # Prevent further code from running if not logged in
    
    if "annotator_comment" not in st.session_state:
        st.session_state["annotator_comment"] = ""

    user_id = st.session_state.user_id
    st.sidebar.title("👤 Annotator Panel")
    st.sidebar.write(f"User: `{user_id}`")
    if st.sidebar.button("🔓 Logout"):
        release_locks(user_id)
        st.session_state.clear()
        st.rerun()

    done, total = get_progress(user_id)
    st.sidebar.markdown(f"**Progress:** {done} / {total}")
    st.sidebar.progress(done / total if total > 0 else 0)

    if "current_image" not in st.session_state or st.session_state.get("fetch_new_image", False):
        row = get_next_image(user_id)
        if not row:
            review_mode()
            return
        st.session_state.current_image = row  # Store the row for this annotation
        st.session_state["fetch_new_image"] = False

    # Load the stored row
    image_name, tweet_text, llm_reasoning = st.session_state.current_image
    st.header("🖼️ Image Annotation")
    image_path = f"{image_name}"
    try:
        st.image(image_path, width=400, caption=image_name)
    except Exception as e:
        st.error(f"Could not load image: {image_name} — {e}")
    
    st.markdown(f"**Tweet Text:** {tweet_text}")
    st.markdown(f"**LLM Reasoning:** {llm_reasoning}")

    st.subheader("🔎 Your Evaluation")
    evidence = st.slider("Evidence Recognition", 1, 5, 3)
    reasoning = st.slider("Reasoning Chain", 1, 5, 3)
    naturalness = st.slider("Text Naturalness", 1, 5, 3)
    st.radio(
        "Accept this reasoning?",
        ["Yes", "No"],
        key="accept_choice"
    )

    # Determine accept_status
    accept_status = 1 if st.session_state.accept_choice == "Yes" else 0

    # Show comment box only if rejected
    if accept_status == 0:
        st.text_area(
            "📝 Comment for Reviewer",
            height=100,
            key="annotator_comment"
        )
    else:
        st.session_state["annotator_comment"] = ""  # Reset when accepted
    if st.button("✅ Submit Annotation"):
        save_annotation(user_id, image_name, evidence, reasoning, naturalness, accept_status, annotator_comment)
        st.success("Annotation submitted!")
        st.session_state.pop("current_image", None)
        st.session_state["fetch_new_image"] = True  
        st.rerun()

if __name__ == "__main__":
    main()
