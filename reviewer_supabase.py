import streamlit as st
import psycopg2
import bcrypt
import datetime

# DB connection
PG_CONFIG = {
    "dbname": st.secrets["dbname"],
    "user": st.secrets["user"],
    "password": st.secrets["password"],
    "host": st.secrets["host"],
    "port": st.secrets["port"]
}

def get_db_connection():
    return psycopg2.connect(**PG_CONFIG)

# Release any locks held by a reviewer
def release_locks(reviewer_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE annotated
        SET locked_by_reviewer = NULL, lock_time_reviewer = NULL
        WHERE locked_by_reviewer = %s
    """, (reviewer_id,))
    conn.commit()
    cur.close()
    conn.close()

# Fetch the next available annotation to review with lock
def get_next_review(reviewer_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        WITH next_item AS (
            SELECT a.image_name, 
                   i.tweet_text, 
                   i.llm_reasoning, 
                   a.evidence_recognition, 
                   a.reasoning_chain, 
                   a.text_naturalness, 
                   a.user_id, 
                   a.accept_status,
                   a.annotator_comment
            FROM annotated a
            JOIN input_data i ON a.image_name = i.image_name
            WHERE a.image_name NOT IN (SELECT image_name FROM reviewed)
                   AND NOT (
                       (a.user_id = 'a4' AND %s = 'a7') OR
                       (a.user_id = 'a5' AND %s = 'a8')
                   )
                   AND (a.locked_by_reviewer IS NULL 
                       OR a.lock_time_reviewer < NOW() - INTERVAL '10 minutes')
            ORDER BY a.image_name
            LIMIT 1
        )
        UPDATE annotated a
        SET locked_by_reviewer = %s, lock_time_reviewer = NOW()
        FROM next_item ni
        WHERE a.image_name = ni.image_name
        RETURNING ni.image_name, ni.tweet_text, ni.llm_reasoning, ni.evidence_recognition, ni.reasoning_chain, ni.text_naturalness, ni.user_id, ni.accept_status, ni.annotator_comment;
    """, (reviewer_id, reviewer_id, reviewer_id))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def login_ui():
    st.title("🔐 Reviewer Login")
    user_id = st.text_input("Reviewer ID")
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
                if role != 'reviewer':
                    st.error("🚫 Access denied: Only reviewers can access this tool.")
                else:
                    st.session_state['user_id'] = user_id
                    st.success("✅ Login successful!")
                    st.rerun()
            else:
                st.error("❌ Incorrect password.")
        else:
            st.error("❌ User ID not found.")
        st.stop()
def get_reviewer_progress(reviewer_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Count completed reviews
    cur.execute("""
        SELECT COUNT(*) 
        FROM reviewed 
        WHERE reviewer_id = %s
    """, (reviewer_id,))
    done = cur.fetchone()[0]
    
    # Count total annotations they are eligible to review
    cur.execute("""
        SELECT COUNT(*) 
        FROM annotated a
        WHERE a.image_name NOT IN (SELECT image_name FROM reviewed)
          AND NOT (
              (a.user_id = 'a4' AND %s = 'a7') OR
              (a.user_id = 'a5' AND %s = 'a8')
          )
    """, (reviewer_id, reviewer_id))
    total = cur.fetchone()[0]
    
    cur.close()
    conn.close()
    return done, done + total  # done + remaining = total
def main():
    if "user_id" not in st.session_state:
        login_ui()
        return

    reviewer_id = st.session_state['user_id']
    st.sidebar.title("👤 Reviewer Panel")
    st.sidebar.write(f"Logged in as: `{reviewer_id}`")

    if st.sidebar.button("🔓 Logout"):
        release_locks(reviewer_id)
        st.session_state.clear()
        st.rerun()

    # Get or keep the current locked review
    if "current_review" not in st.session_state:
        row = get_next_review(reviewer_id)
        if row:
            st.session_state["current_review"] = row
        else:
            st.info("No more annotations left to review.")
            return

    row = st.session_state["current_review"]
    image_name, tweet_text, llm_reasoning, evidence, reasoning, naturalness, contributor_id, accept_status, annotator_comment = row
    done, total = get_reviewer_progress(reviewer_id)
    st.sidebar.markdown(f"**Progress:** {done} / {total}")
    st.sidebar.progress(done / total if total > 0 else 0)
    st.title("CrisisMMD Annotation Reviewer Tool")
    st.image(f"{image_name}", width=400)
    st.markdown(f"**Tweet Text:** {tweet_text}")
    st.markdown(f"**LLM Reasoning:** {llm_reasoning}")
    st.markdown(f"**Evidence Score:** {evidence}")
    st.markdown(f"**Reasoning Score:** {reasoning}")
    st.markdown(f"**Naturalness Score:** {naturalness}")
    st.markdown(f"**Accept Status of LLM Reasoning?:** {'Accepted' if accept_status else 'Rejected'}")
    st.markdown(f"**Annotator Comment:** {annotator_comment if annotator_comment else 'No Comment'}")

    st.markdown("### Reviewer Evaluation")
    if accept_status == 1:
        reviewer_agree = st.radio("Do you agree this needed no correction?", ["Yes (1 pt)", "No (0 pt)"])
        reviewer_score = 1 if "Yes" in reviewer_agree else 0
    else:
        reviewer_score = st.slider("Rate the quality of contributor's revision (1 to 5)", 1, 5, 3)

    final_reasoning = st.text_area("Final Reasoning Output", height=150)

    if st.button("✅ Submit Review"):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO reviewed (image_name, reviewer_id, reviewer_score, final_reasoning, review_time)
            VALUES (%s, %s, %s, %s, %s)
        """, (image_name, reviewer_id, reviewer_score, final_reasoning, datetime.datetime.now()))
        conn.commit()

        # Release lock
        cur.execute("""
            UPDATE annotated
            SET locked_by_reviewer = NULL, lock_time_reviewer = NULL
            WHERE image_name = %s
        """, (image_name,))
        conn.commit()

        # If rejected, delete from annotated
        if (accept_status == 1 and reviewer_score == 0) or (accept_status == 0 and reviewer_score < 4):
            cur.execute("DELETE FROM annotated WHERE image_name = %s", (image_name,))
            conn.commit()
            st.warning("Rejected entry. It will go back for re-annotation.")
        else:
            st.success("Review saved. Entry approved.")

        cur.close()
        conn.close()

        # Move to next image
        del st.session_state["current_review"]
        st.rerun()

if __name__ == "__main__":
    main()







