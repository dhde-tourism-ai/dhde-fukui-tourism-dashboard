import streamlit as st
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

print("hello world")

st.title("🔍 Debugging app.py")

try:
    from dashboard.app import main
    st.write("✅ app.py imported successfully")
    st.write("Calling main()...")
    main()
except Exception as e:
    st.error(f"❌ CRASHED: {type(e).__name__}: {e}")
    import traceback
    st.code(traceback.format_exc())