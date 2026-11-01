import streamlit as st

st.title("Hello from Streamlit")
name = st.text_input("Your name", "Ada")
if st.button("Greet"):
    st.success(f"Hello, {name}, from Streamlit!")
