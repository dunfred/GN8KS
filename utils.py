import os
import re
import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# Function to ensure the directory exists
def ensure_directory_exists(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

# Function to make sure that after restarting the bot, it will properly update old prompt data with latest scrapped data
def update_prompt_output(main_dict, id_key, new_prompt_dict):
    """
    Updates the list of dictionaries within the main dictionary based on the id_key.
    If a dictionary with the same 'prompt' and 'prompt_files' exists, it replaces it. Otherwise, it adds the new dictionary.
    
    :param main_dict: The main dictionary containing the lists.
    :param id_key: The key corresponding to the list within the main dictionary.
    :param new_prompt_dict: The new dictionary to add or replace in the list.
    """
    if id_key not in main_dict:
        main_dict[id_key] = []

    found = False
    for i, item in enumerate(main_dict[id_key]):
        if item['prompt'] == new_prompt_dict['prompt'] and \
            item['prompt_files'] == new_prompt_dict['prompt_files'] and \
            item['prompt_file_urls'] == new_prompt_dict['prompt_file_urls']:

            main_dict[id_key][i] = new_prompt_dict
            found = True
            break
    
    if not found:
        main_dict[id_key].append(new_prompt_dict)


def append_to_excel(file_path, new_data):
    """
    Appends a new row of data to an existing Excel file or creates a new file with the appropriate headers.
    
    :param file_path: The path to the Excel file.
    :param new_data: The new data to append as a pandas Series.
    """
    if os.path.exists(file_path):
        # Load existing data
        existing_data = pd.read_excel(file_path)
        
        # Append new data
        new_df = pd.DataFrame([new_data], columns=existing_data.columns)
        updated_data = pd.concat([existing_data, new_df], ignore_index=True)
        
        # Save to Excel
        updated_data.to_excel(file_path, index=False)
    else:
        # Create a new file with headers and new data
        new_df = pd.DataFrame([new_data])
        new_df.to_excel(file_path, index=False)

# Custom expected condition to wait for any text in the last element that holds Gemini's response
class TextInLastElement:
    def __init__(self, locator):
        self.locator = locator

    def __call__(self, driver):
        elements = driver.find_elements(*self.locator)
        if elements:
            last_element = elements[-1]
            if last_element.text.strip():
                return last_element
        return False

# Custom expected condition to wait for specific text in the last element that holds Gemini's response
class GeminiSpecificTextInLastElement:
    def __init__(self, locator, text):
        self.locator = locator
        self.text = text

    def __call__(self, driver):
        elements = driver.find_elements(*self.locator)
        if elements:
            last_element = elements[-1]
            if self.text in last_element.text or "Analysis unsuccessful" in last_element.text:
                return last_element
        return False

# Custom expected condition to wait for specific text in the last element that holds GPT's response
class GPTSpecificTextInLastElement:
    def __init__(self, locator, text, turn_no, turn_menu_item_locator):
        self.locator = locator
        self.text    = text
        self.turn_no = turn_no
        self.turn_menu_item_locator = turn_menu_item_locator

    def __call__(self, driver):
        elements = driver.find_elements(*self.locator)

        if elements and len(elements) == self.turn_no:
            last_element = elements[-1]
            # print(f'TURN: {self.turn_no} - LAST ELEM:', last_element.text[:50])
            if self.text in last_element.text:
                return last_element
            else:
                try:
                    WebDriverWait(last_element, 1).until(EC.presence_of_element_located(self.turn_menu_item_locator))
                    return last_element
                except Exception:
                    return False
        return False

# Custom expected condition to wait for the last footer element relative to the last content element
class LastFooterElement:
    def __init__(self, content_locator, footer_class):
        self.content_locator = content_locator
        self.footer_class = footer_class

    def __call__(self, driver):
        content_elements = driver.find_elements(*self.content_locator)
        if content_elements:
            last_content_element = content_elements[-1]
            parent_element = last_content_element.find_element(By.XPATH, "./..")
            footer_element = parent_element.find_element(By.XPATH, f"following-sibling::div[contains(@class, '{self.footer_class}')]")
            return footer_element
        return False

def update_error_code_counts(error_counts_dict, string):
    # Define the error types to count
    error_types = [
        'ModuleNotFoundError',
        'FileNotFoundError', 'KeyError', 'ValueError', 'TypeError', 'AttributeError', 
        'NameError', 'SyntaxError'
    ]

    for errorType in error_types:
        error_counts_dict[errorType] += string.count(f"{errorType}:")

def replace_json_tags(notebook_str, base64_images):
    ''' Inserts images (in base 64 format) underneath altair json tags in the notebook string'''
    pattern = r"\[json-tag: code-generated-json-[^]]+\]"
    counter = 0

    def replacement_func(match):
        nonlocal counter
        replacement_text = f"{match.group(0)}"
        if counter < len(base64_images):
            replacement_text = f"![Plot {counter}](data:image/png;base64,{base64_images[counter]})\n{match.group(0)}"
        counter += 1
        return replacement_text

    return re.sub(pattern, replacement_func, notebook_str)

