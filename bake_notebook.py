import os
from nbformat import write
from nbformat.v4 import new_notebook, new_code_cell, new_markdown_cell


class IPYNBGenerator:
    def __init__(self,
                 output_path: str,
                 rater_id:    str = "0", 
                 task_id:     str = "0",
                 nb_for:      str = "Gemini", 
        ) -> None:
        if rater_id == "0":
            raise ValueError('You need to provide a valid rater ID')
        if task_id == "0":
            raise ValueError('You need to provide a valid task ID')

        self.nb_for      = nb_for
        self.rater_id    = rater_id
        self.task_id     = task_id
        self.output_path = output_path

    def text_to_notebook(self, text_dict_list) -> None:
        # Create a new notebook object
        nb = new_notebook()

        # List of cells to add to the notebook
        cells = []

        # Function to process a single notebook string and add its cells to the cells list
        def process_notebook_string(notebook_string):
            lines = notebook_string.split("\n")
            
            blocks = []
            current_block = {"type": "", "content": ""}
            inside_code_block = False
            inside_text_block = False

            for line in lines:
                if line.startswith("```"):
                    if inside_code_block or inside_text_block:
                        if current_block["content"].strip():  # Only add block if content is not empty
                            blocks.append(current_block)
                        current_block = {"type": "", "content": ""}
                        inside_code_block = False
                        inside_text_block = False
                    if "python" in line:
                        current_block["type"] = "code"
                        inside_code_block = True
                    elif "text" in line:
                        current_block["type"] = "text"
                        inside_text_block = True
                elif inside_code_block or inside_text_block:
                    current_block["content"] += line + "\n"
                else:
                    if current_block["content"].strip():  # Only add block if content is not empty
                        blocks.append(current_block)
                    current_block = {"type": "markdown", "content": line + "\n"}
                    blocks.append(current_block)
                    current_block = {"type": "", "content": ""}

            if current_block["content"].strip():
                blocks.append(current_block)

            for block in blocks:
                if block["content"].strip():
                    if block["type"] == "code":
                        cells.append(new_code_cell(block["content"].strip()))
                    elif block["type"] == "text" or block["type"] == "markdown":
                        cells.append(new_markdown_cell(block["content"].strip()))

        # Loop through the list of dictionaries and process each one
        for prompt_index, item in enumerate(text_dict_list):
            user_query = item['prompt']
            notebook_string = item['response']
            prompt_files_str = ",".join([f.split('/')[-1] for f in item['prompt_files']])
            
            # Add a text cell for the user query
            if prompt_index == 0:
                cells.append(new_markdown_cell(f'**User Query:** {user_query}\n\nturn: {prompt_index+1}\n\nfile_name: "{prompt_files_str}"\n\nfile_path: ""'))
            else:
                cells.append(new_markdown_cell(f"**User Query:** {user_query}\n\nturn: {prompt_index+1}"))

            # Process the notebook string and add its cells
            process_notebook_string(notebook_string)

        # Assign cells to the notebook
        nb['cells'] = cells

        # Save the notebook to a file
        filepath = os.path.join(self.output_path, f"{self.nb_for}_rater_{self.rater_id}_ID_{self.task_id}.ipynb")
        with open(filepath, 'w', encoding='utf-8') as f:
            write(nb, f)
        print(f"Notebook has been saved to {filepath}")
