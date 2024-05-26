'''
streamlit run app.py 
'''

import streamlit as st
from nbformat import write
from nbformat.v4 import new_notebook, new_code_cell, new_markdown_cell


def text_to_notebook(text, filename='testNotebook.ipynb'):
    # Create a new notebook object
    nb = new_notebook()
    blocks = text.split('')  # Split text by code block markers

    for block in blocks:
        if 'python' in block:
            # Extract Python code after the first newline
            code = block.split('\n', 1)[1].strip()
            # Add code cell to notebook
            nb['cells'].append(new_code_cell(code))
        elif 'text' in block:
            # Extract error or stdout text after the first newline
            output = block.split('\n', 1)[1].strip()
            # Add markdown cell for the output (error or result)
            nb['cells'].append(new_markdown_cell(f"\n{output}\n"))
        else:
            # Treat non-code/non-text parts as Markdown
            if block.strip():
                nb['cells'].append(new_markdown_cell(block.strip()))

    # Save the notebook to a file
    with open(filename, 'w') as f:
        write(nb, f)
    st.success(f"Notebook has been saved to {filename}")

def main():
    st.title("Generate Notebook from Gemini")

    # Input fields
    data = st.text_input("Data URL:")
    query1 = st.text_area("Query 1:")
    response1 = st.text_area("Response 1:")
    query2 = st.text_area("Query 2:")
    response2 = st.text_area("Response 2:")
    query3 = st.text_area("Query 3:")
    response3 = st.text_area("Response 3:")
    notebook_name = st.text_input("Notebook Filename:", "generated_notebook.ipynb")

    # Button to generate and download the notebook
    if st.button("Generate Notebook"):
        final_target = (
            f"turn 1\n\nQuery: {query1} \n\nData: {data} \n\n" + response1 + "\n\n" +
            f"turn 2\n\nQuery: {query2} \n\nData: {data} \n\n" + response2 + "\n\n" +
            f"turn 3\n\nQuery: {query3} \n\nData: {data} ```\n\n" + response3
        )
        text_to_notebook(final_target, filename=notebook_name)

if __name__ == "_main_":
    main()
