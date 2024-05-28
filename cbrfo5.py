''' 
CLI Based Reproducibility Frequency out of 5 

Runs each task 5 times and stores them as notebooks
'''

# Importing Libraries
import os
import json
import requests
import base64
from PIL import Image
from pprint import pprint
from dotenv import load_dotenv
from nbformat import write
from nbformat.v4 import new_notebook, new_code_cell, new_markdown_cell
from collections import defaultdict
from utils import ensure_directory_exists, update_prompt_output

load_dotenv()

api_key = os.getenv("API_KEY")
model   = os.getenv("MODEL")

url = f"https://preprod-generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={api_key}"
headers = {
    "Content-Type": "application/json"
}

# Reading the File
def read_file_as_base64(file_path):
    with open(file_path, "rb") as file:
        file_contents = file.read()
        encoded_contents = base64.b64encode(file_contents)
        return encoded_contents.decode("utf-8")


try:
    with open('reproducible-jobs.json', 'r') as jfp:
        JOBS = json.loads(jfp.read())
except Exception:
    JOBS = {}
    raise('Please make sure you "reproducible-jobs.json" file is added to this directory before proceeding!')
pprint(JOBS)

RATER_ID = JOBS['rater_id']

# String to notebook generation function
def text_to_notebook(output_path, copy_idx, rater_id, task_id, text_dict_list) -> None:
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
    ensure_directory_exists(os.path.join(output_dir, f"copy_{copy_idx+1}"))

    filepath = os.path.join(output_path, f"copy_{copy_idx+1}", f"Gemini_rater_{rater_id}_ID_{task_id}.ipynb")
    with open(filepath, 'w', encoding='utf-8') as f:
        write(nb, f)
    print(f"Notebook has been saved to {filepath}")




for task in JOBS['tasks']:
    OUTPUT = defaultdict(list)
    
    task_id        = task['task_id']
    prompt_files   = task['files'][0:1] # Use first file only

    # Ensure the output directory exists
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, 'reproduced_outputs', f"ID_{task_id}")
    ensure_directory_exists(output_dir)

    for copy_index in range(5):
        print(f'[x] Started Task ID: {task_id} {copy_index+1}/5.')

        # Create a new dict object
        data = {
            "model": model,
            # candidate count controls how many responses are generated
            "generationConfig": {"candidateCount": 3},
            "contents": [
                # user query with an uploaded file
                # {
                #     "role": "user",
                #     "parts": [
                #         # this is the bit that uploads the file, mimeType is:
                #         #     "text/csv" for text data
                #         #     "application/vnd.ms-excel" for xls
                #         #     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" for xlsx
                #         # it's good to add the filename as sometimes some information is included in the filename
                        
                #     ]
                # }
            ]
        }
        is_first_turn = True
        files_uploaded = False

        for p_idx, prompt in enumerate(task['prompts']):
            notebook_str = """"""
            is_first_turn = p_idx==0

            # Copy output dir
            resp_dir_path = os.path.join(output_dir, f"copy_{copy_index+1}")
            ensure_directory_exists(resp_dir_path)

            if is_first_turn:
                # Add this turn's prompt
                print('[x] Is first turn')

                if not files_uploaded or prompt_files:
                    print('[x] Submiting first prompt with file')

                    # Can only upload one file 
                    p_filepath = prompt_files[0]
                    p_filepath     = p_filepath.strip()
                    file_name      = p_filepath.split('/')[-1]
                    file_extention = file_name.split('.')[-1]
                    
                    if file_extention == 'xlsx':
                        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

                    elif file_extention == 'xls':
                        mime_type = "application/vnd.ms-excel"

                    else:
                        mime_type = "text/csv"

                    file_encoded = read_file_as_base64(p_filepath)


                    data['contents'].append(
                        {
                            "role": "user",
                            "parts": [
                                {"text": prompt},
                                {
                                    "inlineData": {"mimeType": mime_type, "data":file_encoded}, 
                                    "partMetadata": {"externalFileMetadata": {"name": file_name}}
                                }
                            ]
                        }
                    )
                    files_uploaded = True
                else:
                    data['contents'].append({
                        "role": "user",
                        "parts": [{ "text": prompt } ]
                    })
                response = requests.post(url, headers=headers, data=json.dumps(data))
                print('[x] MODEL RESPONSE RECEIVED',response)

            else:
                print('[x] Loading previous turn data')
                with open(f"{resp_dir_path}/response-turn{p_idx}.json","r") as f: # Read previous turn data
                    prev_response = json.loads(f.read())
                    print('[x] Done Loading previous turn data')
                    # Grab the previous turn data and append new query data to it
                    contents_of_prev_turn = prev_response["candidates"][0]["content"]
                    contents_of_prev_turn['parts'] = [d for d in contents_of_prev_turn['parts'] if 'fileData' not in d]

                    # New query
                    new_query = {
                        "role": "user",
                        "parts": [
                            {"text": prompt},
                        ]
                    }

                    # append model response and new query
                    data["contents"].append(contents_of_prev_turn)
                    data["contents"].append(new_query)

                    print('[x] Submiting New Query to Model')

                    response = requests.post(url, headers=headers, data=json.dumps(data))
                    print('[x] Query Response Received',response)

            # Save the Response in a Json File
            with open(f"{resp_dir_path}/response-turn{p_idx+1}.json","w") as f:
                f.write(json.dumps(response.json(),indent=4))

            # Parse and Generate Notebook String from Turn Output
            try:
                for i in response.json()["candidates"][0]["content"]["parts"][3]["structuredData"]["advancedIceFlow"]["iceFlowState"]["events"]:
                    if i['eventTag'] in [
                        'EVENT_TAG_CODE',
                        'EVENT_TAG_CODE_MSG_OUT',
                        'EVENT_TAG_CODE_ERROR_OUT',
                        'EVENT_TAG_OUTPUT_TO_USER',
                    ]:
                        if i['eventTag'] == 'EVENT_TAG_CODE':
                            notebook_str += f"```python?code_reference&code_event_index=2\n{i['eventMsg']}\n```\n"

                        elif i['eventTag'] in ['EVENT_TAG_CODE_MSG_OUT','EVENT_TAG_CODE_ERROR_OUT']:
                            notebook_str += f"```text?code_stdout&code_event_index=2\n{i['eventMsg']}\n```\n"
                        else:
                            notebook_str += i['eventMsg'] + "\n"
            except IndexError:
                # Model probably encountered an error when executing prompt
                event_msg = response.json()["candidates"][0]["content"]["parts"][0]['text']
                notebook_str += event_msg

            # Update the local backup data with latest prompt data if already exists, else add as new
            update_prompt_output(
                main_dict       = OUTPUT,
                id_key          = task_id,
                new_prompt_dict =   {
                    'prompt': prompt,
                    'response': notebook_str,
                    'prompt_files': prompt_files,
                    'prompt_file_urls': []
                }
            )

            # Save Images For this Turn (if any)
            parts = response.json()["candidates"][0]["content"]["parts"]

            # recover png images, of course different file types can be identified
            images = [x for x in parts if "fileData" in x.keys() and ("png" in x["partMetadata"]["tag"])]
            links = [x["fileData"]["fileUri"] for x in images]

            for im_idx, l in enumerate(links):
                im = Image.open(requests.get(l, stream=True).raw)
                ensure_directory_exists(os.path.join(output_dir, f"copy_{copy_index+1}"))
                filepath = f"{output_dir}/copy_{copy_index+1}/Gemini_userquery{p_idx+1}_plot{im_idx+1}.png"
                im.save(filepath)
            print(f'[x] Saved all images for turn {p_idx+1}')

        # Generate notebook
        print('Generating Notebook')
        text_to_notebook(
            output_path     = output_dir,
            copy_idx        = copy_index,
            rater_id        = RATER_ID,
            task_id         = task_id,
            text_dict_list  = OUTPUT[task_id]
        )

        print(f'[x] Completed Task ID: {task_id} {copy_index+1}/5.')




