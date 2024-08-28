import json
import os
import re
from bs4 import BeautifulSoup
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
                        current_block["type"] = "markdown"
                        inside_text_block = True
                elif inside_code_block or inside_text_block:
                    current_block["content"] += line + "\n"
                else:
                    if current_block["content"].strip():  # Only add block if content is not empty
                        blocks.append(current_block)
                    current_block = {"type": "text", "content": line + "\n"}
                    blocks.append(current_block)
                    current_block = {"type": "", "content": ""}

            if current_block["content"].strip():
                blocks.append(current_block)

            for block in blocks:
                if block["content"].strip():
                    if block["type"] == "code":
                        cells.append(new_code_cell(block["content"].strip()))
                    elif block["type"] == "text":
                        cells.append(new_markdown_cell(block["content"].strip()))
                    elif block["type"] == "markdown":
                        cells.append(new_markdown_cell( "```\n" + block["content"].strip()  + "\n```\n"))

        # Loop through the list of dictionaries and process each one
        for prompt_index, item in enumerate(text_dict_list):
            user_query = item['prompt']
            notebook_string = item['response_with_image']
            prompt_files_str = ",".join([f.split('/')[-1] for f in item['prompt_files']])
            prompt_file_urls = ", ".join(item["prompt_file_urls"])
            
            # Add a text cell for the user query
            if prompt_index == 0:
                cells.append(new_markdown_cell(f'**User Query:** {user_query}\n\nturn: {prompt_index+1}\n\nfile_name: "{prompt_files_str}"\n\nfile_path: "{prompt_file_urls}"'))
            else:
                cells.append(new_markdown_cell(f"**User Query:** {user_query}\n\nturn: {prompt_index+1}"))

            # Process the notebook string and add its cells
            process_notebook_string(notebook_string)

        # Assign cells to the notebook
        nb['cells'] = cells

        # Save the notebook to a file
        filepath = os.path.join(self.output_path, f"{self.nb_for}_rater_{self.rater_id}_ID_{self.task_id}_GN8K.ipynb")
        with open(filepath, 'w', encoding='utf-8') as f:
            write(nb, f)
        print(f"Notebook has been saved to {filepath}")
        return f"{self.nb_for}_rater_{self.rater_id}_ID_{self.task_id}_GN8K.ipynb"

    def html_to_notebook(self, html_dict_list):
        notebook_cells = []

        # Loop through the list of dictionaries and process each one
        for prompt_index, item in enumerate(html_dict_list):
            user_query = item['prompt']
            html_content = item['html_response']
            prompt_files_str = ",".join([f.split('/')[-1] for f in item['prompt_files']])
            c_prompt_file_urls = ", ".join(item["prompt_file_urls"])

            # Add a text cell for the user query
            if prompt_index == 0:
                notebook_cells.append({
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": [f'**User Query:** {user_query}\n\nturn: {prompt_index+1}\n\nfile_name: "{prompt_files_str}"\n\nfile_path: "{c_prompt_file_urls}"\n']
                    })

            else:
                notebook_cells.append({
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": [f"**User Query:** {user_query}\n\nturn: {prompt_index+1}\n"]
                    })

            soup = BeautifulSoup(html_content, 'html.parser')

            seen_li_elems = set()
            img_counter = 1
            for tag in soup.find_all(['p', 'pre', 'h3', 'ol', 'ul','img']):
                if tag.name == 'p':
                    # Find all <code> tags and replace them with backticks
                    for code_tag in tag.find_all('code'):
                        code_tag.insert_before('`')
                        code_tag.insert_after('`')
                        code_tag.unwrap()
                    # Find all <strong> tags and replace them with astericks
                    for code_tag in tag.find_all('strong'):
                        code_tag.insert_before('**')
                        code_tag.insert_after('**')
                        code_tag.unwrap()
                        
                    notebook_cells.append({
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": [tag.get_text() + "\n"]
                    })
                elif tag.name == 'pre':
                    code_content = tag.find('code')
                    if code_content:
                        notebook_cells.append({
                            "cell_type": "code",
                            "metadata": {},
                            "source": [cl + '\n' for cl in code_content.get_text().splitlines()]
                        })
                    else:
                         notebook_cells.append({
                            "cell_type": "markdown",
                            "metadata": {},
                            "source": ["```\n" + tag.get_text() + "\n```\n"]
                        })
                elif tag.name == 'h3':
                    notebook_cells.append({
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": ["### " + tag.get_text() + "\n"]
                    })
                elif tag.name == 'ol':
                    duplicate = False
                    for seen_li in seen_li_elems:
                        if str(tag) in seen_li:
                            duplicate = True

                    if not duplicate:
                        list_items = self.process_nested_list(tag, ordered=True)
                        notebook_cells.append({
                            "cell_type": "markdown",
                            "metadata": {},
                            "source": [list_items + "\n"]
                        })
                        seen_li_elems.add(str(tag))

                elif tag.name == 'ul':
                    duplicate = False
                    for seen_li in seen_li_elems:
                        if str(tag) in seen_li:
                            duplicate = True

                    if not duplicate:
                        list_items = self.process_nested_list(tag, ordered=False)
                        notebook_cells.append({
                            "cell_type": "markdown",
                            "metadata": {},
                            "source": [list_items + "\n"]
                        })
                        seen_li_elems.add(str(tag))

                elif tag.name == 'img':
                    pattern = r'<img[^>]*src="([^"]*)"'
                    # Search for the pattern
                    match = re.search(pattern, str(tag))

                    # Check if a match was found and print the src value
                    if match:
                        base64_image = match.group(1)                    
                        img_base64_str = f'![Plot {img_counter}](data:image/png;base64,{base64_image})'
                        notebook_cells.append({
                                "cell_type": "markdown",
                                "metadata": {},
                                "source": [img_base64_str + "\n"]
                            })
                        img_counter += 1

        # Notebook JSON structure
        notebook = {
            "cells": notebook_cells,
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 4
        }
        notebook_str = json.dumps(notebook, indent=0)

        # Save the notebook to a file
        filepath = os.path.join(self.output_path, f"{self.nb_for}_rater_{self.rater_id}_ID_{self.task_id}_GN8K.ipynb")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(notebook_str)
        print(f"[x] Notebook has been saved to {filepath}")
        return f"{self.nb_for}_rater_{self.rater_id}_ID_{self.task_id}_GN8K.ipynb"

    def process_nested_list(self, tag, level=0, ordered=False):
        items = []
        indent = '  ' * level
        prefix_no = 0
        seen_list_elems = set()

        for li in tag.find_all('li', recursive=False):
            nested_ul = li.find('ul')
            nested_ol = li.find('ol')

            # Temporarily remove nested lists
            if nested_ul:
                nested_ul.extract()
            if nested_ol:
                nested_ol.extract()

            # Get the text for the current list item
            prefix = f'{prefix_no+1}. ' if ordered else '- '

            # Find all <code> tags and replace them with backticks
            for code_tag in li.find_all('code'):
                code_tag.insert_before('`')
                code_tag.insert_after('`')
                code_tag.unwrap()

            # # Find all <strong> tags and replace them with astericks
            for code_tag in li.find_all('strong'):
                code_tag.insert_before('**')
                code_tag.insert_after('**')
                code_tag.unwrap()

            items.append(indent + prefix + li.get_text().strip())
            seen_list_elems.add(indent + prefix + li.get_text().strip())

            # Reinsert and process nested lists
            if nested_ul and nested_ul not in seen_list_elems:
                items.append(self.process_nested_list(nested_ul, level + 1, ordered=False))
                li.append(nested_ul)
                seen_list_elems.add(nested_ul)

            if nested_ol and nested_ul not in seen_list_elems:
                items.append(self.process_nested_list(nested_ol, level + 1, ordered=True))
                li.append(nested_ol)
                seen_list_elems.add(nested_ol)
            prefix_no += 1
        return '\n'.join(items)


