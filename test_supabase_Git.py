<<<<<<< HEAD
import streamlit as st
import psycopg2


SUPABASE_DB_CONFIG = {
    "dbname": st.secrets["db"]["dbname"],
    "user": st.secrets["db"]["user"],
    "password": st.secrets["db"]["password"],
    "host": st.secrets["db"]["host"],
    "port": "5432"

}

def connection_check():
    try:
        conn = psycopg2.connect(**SUPABASE_DB_CONFIG)
        cur = conn.cursor()
        st.header("✅ Connected successfully into Supabase.")
        cur.close()
        conn.close()
    except Exception as e:
        print("❌ Connection failed:", e)

connection_check()

=======
import streamlit as st
import psycopg2


SUPABASE_DB_CONFIG = {
    "dbname": st.secrets["db"]["dbname"],
    "user": st.secrets["db"]["user"],
    "password": st.secrets["db"]["password"],
    "host": st.secrets["db"]["host"],
    "port": "5432"

}

def connection_check():
    try:
        conn = psycopg2.connect(**SUPABASE_DB_CONFIG)
        cur = conn.cursor()
        st.header("✅ Connected successfully into Supabase.")
        cur.close()
        conn.close()
    except Exception as e:
        print("❌ Connection failed:", e)

connection_check()

>>>>>>> aa2f7b47 (Added images folder)
