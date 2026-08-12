import streamlit as st

from graph.workflow import graph

st.set_page_config(
    page_title="ResearchForge",
    page_icon="🔬",
    layout="wide"
)

st.title("🔬 ResearchForge")
st.subheader("General-Purpose Multi-Agent AI Research Workforce")

query = st.text_area(
    "Research Question",
    placeholder="Enter your research question..."
)

if st.button("Start Research"):

    if not query.strip():
        st.warning("Please enter a research question.")
    else:

        with st.spinner("Starting research workflow..."):

            result = graph.invoke({
                "message": query
            })

        st.success("Workflow completed")

        st.write(result)