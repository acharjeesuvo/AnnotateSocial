import streamlit as st
import psycopg2
import bcrypt
import datetime

# DB connection
PG_CONFIG = {
    "host": st.secrets["db"]["host"],
    "port": st.secrets["db"]["port"],
    "dbname": st.secrets["db"]["dbname"],
    "user": st.secrets["db"]["user"],
    "password": st.secrets["db"]["password"]
}

def get_db_connection():
    return psycopg2.connect(**PG_CONFIG)

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

def main():
    if "user_id" not in st.session_state:
        login_ui()
        return

    st.sidebar.title("👤 Reviewer Panel")
    reviewer_id = st.session_state['user_id']
    st.sidebar.write(f"Logged in as: `{reviewer_id}`")
    if st.sidebar.button("🔓 Logout"):
        st.session_state.clear()
        st.rerun()

    st.title("CrisisMMD Annotation Reviewer Tool")
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM annotated
        WHERE image_name NOT IN (SELECT image_name FROM reviewed)
        LIMIT 1
    """)
    row = cur.fetchone()

    if row:
        image_name, tweet_text, llm_reasoning, evidence, reasoning, naturalness, contributor_id, accept_status = row

        st.image(f"images/{image_name}", width=400)
        st.markdown(f"**Tweet Text:** {tweet_text}")
        st.markdown(f"**LLM Reasoning:** {llm_reasoning}")
        st.markdown(f"**Evidence Score:** {evidence}")
        st.markdown(f"**Reasoning Score:** {reasoning}")
        st.markdown(f"**Naturalness Score:** {naturalness}")

        st.markdown("### Reviewer Evaluation")

        if accept_status == 1:
            reviewer_agree = st.radio("Do you agree this needed no correction?", ["Yes (1 pt)", "No (0 pt)"])
            reviewer_score = 1 if "Yes" in reviewer_agree else 0
        else:
            reviewer_score = st.slider("Rate the quality of contributor's revision (1 to 5)", 1, 5, 3)

        final_reasoning = st.text_area("Final Reasoning Output", height=150)

        if st.button("Submit Review"):
            cur.execute("""
                INSERT INTO reviewed (image_name, reviewer_id, reviewer_score, final_reasoning, review_time)
                VALUES (%s, %s, %s, %s, %s)
            """, (image_name, reviewer_id, reviewer_score, final_reasoning, datetime.datetime.now()))
            conn.commit()

            if (accept_status == 1 and reviewer_score == 0) or (accept_status == 0 and reviewer_score < 4):
                cur.execute("DELETE FROM annotated WHERE image_name = %s", (image_name,))
                conn.commit()
                st.warning("Rejected entry. It will go back for re-annotation.")
            else:
                st.success("Review saved. Entry approved.")

            st.rerun()
    else:
        st.info("No more annotations left to review.")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()