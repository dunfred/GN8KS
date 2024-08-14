''' This tool fetches queries from the Gemini vs GPT Comparative tracker, generates the notebooks and updates tracker
'''

import base64
import os
import re
import time
import json
import random
import pyautogui
import pyperclip
import platform
import pandas as pd
from pathlib import Path
from copy import deepcopy
from datetime import datetime
from selenium import webdriver
from collections import defaultdict
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from pynput.keyboard import Key as PyKey, Controller
from pprint import pprint
from bake_notebook import IPYNBGenerator
from process_and_update_tracker import TaskProcessor
from utils import LastFooterElement, TextInLastElement, GeminiSpecificTextInLastElement, append_to_excel, ensure_directory_exists, replace_json_tags, update_error_code_counts, update_prompt_output


try:
    with open('gemini-outputs.json', 'r') as of:
        OUTPUT = defaultdict(list, json.loads(of.read()))  # Convert to defaultdict type
except Exception:
    OUTPUT = defaultdict(list)

print("OS:\t",platform.system())
print("Type:\t",platform.machine())

def get_chromedriver_path():
    # Supports linux64, mac-arm64, mac-x64, win32 and win64 arc
    system = platform.system()
    arch = platform.machine()
    
    if system == "Linux":
        return "webdrivers/chromedriver-linux64"
    elif system == "Darwin":
        if arch == "arm64":
            return "webdrivers/chromedriver-mac-arm64"
        else:
            return "webdrivers/chromedriver-mac-x64"
    elif system == "Windows":
        if arch.endswith("64"):
            return "webdrivers/chromedriver-win64.exe"
        else:
            return "webdrivers/chromedriver-win32.exe"
    else:
        raise Exception("Unsupported operating system")

# Supports linux64, mac-arm64, mac-x64, win32 and win64 arc
system = platform.system()
arch = platform.machine()
# Get the system's username
system_username = os.getlogin()
print('System Username:', system_username)

# Initialize WebDriver with the appropriate ChromeDriver
chromedriver_path = get_chromedriver_path()
print('Chrome Driver Path:', chromedriver_path)

# Configure Chrome options
options = Options()
# options.add_argument("--headless")
options.add_argument("--disable-gpu")  # This option is recommended to avoid hardware acceleration issues
options.add_argument("--window-size=1920,1080")  # You can specify your desired window size
options.add_argument('--no-sandbox')

# Path to your existing user profile
if system == "Windows":
    options.add_argument(r'--user-data-dir=C:\selenium_chrome_profile')

elif system == "Darwin":
    options.add_argument(f'--user-data-dir=/Users/{system_username}/selenium_chrome_profile')

elif system == "Linux":
    options.add_argument(f'--user-data-dir=/home/{system_username}/selenium_chrome_profile')

else:
    raise Exception("Unsupported operating system")

# options.add_experimental_option("debuggerAddress", "localhost:9222") # Your Gemini's chrome profile port would be on port "9222"
options.add_argument("--disable-blink-features=AutomationControlled")

# Function to introduce random delays
def random_delay(a=2, b=5):
    time.sleep(random.uniform(a, b))

# Initialize WebDriver with the appropriate ChromeDriver
service = ChromeService(executable_path=chromedriver_path)
driver = webdriver.Chrome(service=service, options=options)

# print("[x] The script will wait 10 seconds to make sure everything is loaded.")
# time.sleep(10)

# # Get the screen size
screen_width = driver.execute_script("return screen.width;")
screen_height = driver.execute_script("return screen.height;")

# Calculate the window size and position
window_width = int(screen_width * 0.8) if int(screen_width * 0.8) < 1180 else 1180
window_height = screen_height if screen_height < 1080 else 1080
# window_x = 0  # Align to the left
# window_y = 0
print('window_width', window_width)
print('window_height', window_height)

# Set the window size and position
driver.set_window_rect(width=window_width, height=window_height)
# driver.set_window_rect(x=window_x, y=window_y, width=window_width, height=window_height)


# Initialize the task processor
processor = TaskProcessor()

# Fetch tasks with status "Added Query"
# Open a new session and run all prompts for each task/job
tasks = processor.fetch_new_task()

XON = True if len(tasks) > 0 else False

while XON:
    # Run if there are new tasks
    for task in tasks:
        RATER_ID = str(task['Rater ID']).strip()

        task_id = task['TASK_ID']
        try:
            # Read All FIles Links
            input_files_1 = task.get("Input File(s) \nTurn 1", None)
            input_files_2 = task.get("Input File(s) \nTurn 2", None)
            input_files_3 = task.get("Input File(s) \nTurn 3", None)
            
            # Read All Queries   
            query_1 = task.get("Prompt\nTurn 1", None)
            query_2 = task.get("Prompt\nTurn 2", None)
            query_3 = task.get("Prompt\nTurn 3", None)

            # Parse and Combine the data into a dict
            
            TASK_PROMPTS = [str(q).strip() for q in [query_1, query_2, query_3] if q]


            prompt_file_urls = [str(i).strip() for i in set([input_files_1, input_files_2, input_files_3]) if i]
            prompt_files      = [
                # Get local file path of input files (download if doesn't exist)
                processor.get_file_name_from_drive_link_and_download(f_url) for f_url in prompt_file_urls
            ]

            files_uploaded = False

            if TASK_PROMPTS: # Continue if prompts are available
                # Ensure the output directory exists
                base_dir = os.path.dirname(os.path.abspath(__file__))
                output_dir = os.path.join(base_dir, 'notebooks', f"ID_{task_id}")
                ensure_directory_exists(output_dir)

                print(f'[x] Started Task ID: {task_id}.')

                # Set the status of the tracker row to indicate it's been worked on
                row_index = processor.get_task_row_index(task_id)
                processor.sheet.update_cell(row_index, processor.sheet.find("GN8K Status").col, "Tool In Progress")

                # Open Gemini
                driver.get('https://gemini.google.com/')

                ERROR_COUNTS_DICT = defaultdict(int, {
                    'ModuleNotFoundError': 0,
                    'FileNotFoundError': 0, 
                    'KeyError': 0, 
                    'ValueError': 0, 
                    'TypeError': 0, 
                    'AttributeError': 0, 
                    'NameError': 0, 
                    'SyntaxError': 0
                })

                try:
                    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.TAG_NAME, 'bard-sidenav-content')))
                    main_container_tag_name = 'bard'
                except Exception:
                    main_container_tag_name = 'mat'

                for idx, user_query in enumerate(TASK_PROMPTS):
                    print(f'[x] {task_id} - Starting Prompt {idx+1}: {user_query}')
                    # Find the input text field elem
                    input_text_elem_xpath = f'//*[@id="app-root"]/main/side-navigation-v2/{main_container_tag_name}-sidenav-container/{main_container_tag_name}-sidenav-content/div/div/div[2]/chat-window/div[1]/div[2]/div[1]/input-area-v2/div/div/div[1]/div/div[1]/rich-textarea/div[1]'

                    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, input_text_elem_xpath)))

                    # Generate full path to all prompt files
                    files_str = list(map(lambda x: str(Path(x).resolve()), prompt_files))

                    prompt_elem = driver.find_element(By.XPATH, input_text_elem_xpath)
                    prompt_elem.send_keys(user_query)

                    # Find the file input element by its name or ID
                    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, input_text_elem_xpath)))
                    is_first_file = True

                    # Ensures all files are uploaded just once.
                    if not files_uploaded:
                        for file in files_str:
                            try:
                                upload_files_elem_xpath = '//button[@aria-label="Open upload file menu" and contains(@class, "upload-card-button")]'
                                WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, upload_files_elem_xpath)))
                                print('Upload Files Elem Exists')
                            except Exception:
                                if is_first_file:
                                    upload_files_elem_xpath = f'//*[@id="app-root"]/main/side-navigation-v2/{main_container_tag_name}-sidenav-container/{main_container_tag_name}-sidenav-content/div/div/div[2]/chat-window/div[1]/div[2]/div[1]/input-area-v2/div/div/div[2]/div/uploader/div[1]/div/button'
                                else:
                                    upload_files_elem_xpath = f'//*[@id="app-root"]/main/side-navigation-v2/{main_container_tag_name}-sidenav-container/{main_container_tag_name}-sidenav-content/div/div/div[2]/chat-window/div[1]/div[2]/div[1]/input-area-v2/div/div/div[3]/div/uploader/div[1]/div/button'

                                WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, upload_files_elem_xpath)))
                            driver.find_element(By.XPATH, upload_files_elem_xpath).click()

                            upload_local_file_xpath = '//*[@id="file-uploader-local"]'
                            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, upload_local_file_xpath)))
                            local_file_input = driver.find_element(By.XPATH, upload_local_file_xpath)
                            local_file_input.click() 
                            time.sleep(3)

                            # Do this for Mac
                            if platform.system() == 'Darwin':
                                pyautogui.hotkey('command', 'shift', 'g')  # Shortcut to open 'Go to Folder' dialog on Mac
                                time.sleep(1)  # Ensure the dialog is focused
                                # Simulate typing the file path using pyautogui
                                pyautogui.write(file, interval=0.05)
                                pyautogui.press('enter')
                                time.sleep(1)
                                pyautogui.press('enter')
                            # Do this for other OS
                            else:
                                keyboard = Controller()
                                keyboard.type(file)
                                keyboard.press(PyKey.enter)
                                keyboard.release(PyKey.enter)

                            is_first_file = False
                            print(f'[x] Prompt {idx+1}: File Uploaded Successfully! - {file}')
                        # Make sure script doesn't attempt to upload files again.
                        files_uploaded = True
                        time.sleep(3)

                    # Only wait this long if files were uploaded in this turn
                    if not is_first_file: # This variable will always be False whenever a file is uploaded
                        print('[x] Waiting a couple more seconds after file upload before cliking submit button.')
                        time.sleep(5)
                        # time.sleep(20)

                    # Submit the query.
                    submit_prompt_btn_xpath = '//button[@aria-label="Send message" and contains(@class, "send-button")]'
                    # submit_prompt_btn_xpath = f'//*[@id="app-root"]/main/side-navigation-v2/{main_container_tag_name}-sidenav-container/{main_container_tag_name}-sidenav-content/div/div/div[2]/chat-window/div[1]/div[2]/div[1]/input-area-v2/div/div/div[4]/div/div/button'

                    try:
                        WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, submit_prompt_btn_xpath)))
                    except Exception:
                        submit_prompt_btn_xpath = f'//*[@id="app-root"]/main/side-navigation-v2/{main_container_tag_name}-sidenav-container/{main_container_tag_name}-sidenav-content/div/div/div[2]/chat-window/div[1]/div[2]/div[1]/input-area-v2/div/div/div[3]/div/div/button'
                        try:
                            WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, submit_prompt_btn_xpath)))
                        except Exception:
                            submit_prompt_btn_xpath = f'//*[@id="app-root"]/main/side-navigation-v2/{main_container_tag_name}-sidenav-container/{main_container_tag_name}-sidenav-content/div/div/div[2]/chat-window/div[1]/div[2]/div[1]/input-area-v2/div/div/div[2]/div/div[2]/button'
                            try:
                                WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, submit_prompt_btn_xpath)))
                            except Exception:
                                submit_prompt_btn_xpath = f'//*[@id="app-root"]/main/side-navigation-v2/{main_container_tag_name}-sidenav-container/{main_container_tag_name}-sidenav-content/div/div[2]/chat-window/div[1]/div[2]/div[1]/input-area-v2/div/div/div[1]/div/div[1]/rich-textarea/div[1]'
                                WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, submit_prompt_btn_xpath)))

                    submit_prompt_btn = driver.find_element(By.XPATH, submit_prompt_btn_xpath)
                    try:
                        submit_prompt_btn.click()
                    except Exception:
                        time.sleep(30) # Wait 30 more seconds and try again
                        submit_prompt_btn = driver.find_element(By.XPATH, submit_prompt_btn_xpath)
                        submit_prompt_btn.click()

                    # Define the locator for the element you want to observe
                    observed_element_locator = (By.CSS_SELECTOR, "[class^='response-container-content']")
                    start_time_to_trigger_ice = time.time()

                    # Wait for the element to be present
                    WebDriverWait(driver, 90).until(EC.presence_of_element_located(observed_element_locator))

                    # Wait for the text "Analyzing..." to appear in the element or its nested elements
                    WebDriverWait(driver, 310).until(TextInLastElement(observed_element_locator))

                    # End timing
                    end_time_to_trigger_ice = time.time()

                    # Calculate the elapsed time
                    time_to_trigger_ice = round(end_time_to_trigger_ice - start_time_to_trigger_ice, 2)
                    print(f"[x] Prompt {idx+1} Time To Trigger ICE: {time_to_trigger_ice} seconds")

                    # Continue to wait for the specific text "Analysis complete" for next 5 minutes
                    WebDriverWait(driver, 300).until(GeminiSpecificTextInLastElement(observed_element_locator, "Analysis complete"))

                    # Record the time when "Analysis complete" or "Analysis unsuccessful" appears
                    analysis_complete_time = time.time()
                    end_to_end_time = round(analysis_complete_time - start_time_to_trigger_ice, 2)
                    print(f"[x] Prompt {idx+1} End To End Time: {end_to_end_time} seconds")

                    elements = driver.find_elements(*observed_element_locator)
                    if elements:
                        gemini_reponse_elem = elements[-1]
                    else:
                        gemini_reponse_elem = None

                    # Define the locator for the footer elements
                    response_footer_locator = (By.XPATH, "following-sibling::div[contains(@class, 'response-container-footer')]")

                    # Wait for the last footer element to be present
                    response_footer_element = WebDriverWait(driver, 310).until(LastFooterElement(observed_element_locator, "response-container-footer"))
                    # print("RESPONSE FOOTER ELEM:", response_footer_element)

                    time.sleep(3)
                    # Finding and clicking menu action bar to show copy button
                    more_options_menu_element_xpath = ".//message-actions/div/div/div[2]/button"
                    try:
                        WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, )))
                    except Exception:
                        # Scroll to the bottom of the page
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        # Now try again
                        more_options_menu_element_xpath = './/*[@aria-label="Show more options" and @mattooltip="More" and contains(@class, "-mdc-menu-trigger")]'
                        WebDriverWait(driver, 90).until(EC.element_to_be_clickable((By.XPATH, more_options_menu_element_xpath)))

                    more_options_menu = response_footer_element.find_element(By.XPATH, more_options_menu_element_xpath)
                    more_options_menu.click()

                    # Finding and clicking the actual copy button
                    copy_response_xpath = "//*[contains(@id, 'mat-menu-panel-')]/div/div/button"
                    WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, copy_response_xpath)))
                    copy_response_button = response_footer_element.find_element(By.XPATH, copy_response_xpath)
                    copy_response_button.click()

                    # Use JavaScript to get the attribute value
                    response_ngcontent_id = driver.execute_script("return arguments[0].getAttributeNames().find(name => name.startsWith('_ngcontent-'))", gemini_reponse_elem)
                    # print("Response ID:", response_ngcontent_id)

                    # Find all img elements within the response element that have the ngcontent attribute
                    plot_images = gemini_reponse_elem.find_elements(By.TAG_NAME, 'img')
                    plot_images = [i for i in plot_images if str(i.get_attribute('alt')).lower().strip() == "chart shown as an image"]

                    # Iterate through each plot image and save it
                    for img_idx, img in enumerate(plot_images):
                        # Get the src attribute, which contains the base64 encoded image
                        src = img.get_attribute('src')
                        alt = img.get_attribute('alt')

                        # Remove the base64 prefix
                        if 'base64,' in src:
                            base64_data = src.split('base64,')[1]
                        else:
                            base64_data = src

                        # Decode the base64 data and save the image
                        img_data = base64.b64decode(base64_data)
                        file_path = os.path.join(output_dir, f'Gemini_userquery{idx+1}_plot{img_idx+1}.png')

                        with open(file_path, 'wb') as file:
                            file.write(img_data)

                    time.sleep(3)

                    notebook_response = pyperclip.paste()
                    notebook_response_copy = deepcopy(notebook_response)

                    # Find all traceback blocks
                    tracebacks_str = "\n".join(re.findall(r'Traceback \(most recent call last\):.*?(?=\n\n|\Z)', notebook_response_copy, re.DOTALL))

                    # Count all error codes witnessed in this turn's outputs
                    update_error_code_counts(
                        ERROR_COUNTS_DICT,
                        tracebacks_str
                    )

                    # Perform the insertion of plot images into notebook string
                    notebook_response_copy = replace_json_tags(
                        notebook_str=notebook_response_copy,
                        base64_images=[
                            img.get_attribute('src').split('base64,')[1] if 'base64,' in img.get_attribute('src')\
                            else img.get_attribute('src')\
                            for img in plot_images
                        ]
                    )

                    # Update the local backup data with latest prompt data if already exists, else add as new
                    update_prompt_output(
                        main_dict       = OUTPUT,
                        id_key          = task_id,
                        new_prompt_dict =   {
                            'prompt': user_query,
                            'time_to_ice': time_to_trigger_ice,
                            'end_to_end_time': end_to_end_time,
                            'response': notebook_response,
                            'response_with_image': notebook_response_copy,
                            'prompt_files': prompt_files,
                            'prompt_file_urls': prompt_file_urls,
                            'timestamp': str(datetime.now()),
                            **ERROR_COUNTS_DICT
                        }
                    )
                    
                    # Create local update/backup
                    with open('gemini-outputs.json', 'w') as out:
                        out.write(json.dumps(OUTPUT))


                    new_data = pd.Series({
                        'rater_id': RATER_ID,
                        'task_id': task_id,
                        'prompt': user_query,
                        'time_to_ice': time_to_trigger_ice,
                        'end_to_end_time': end_to_end_time,
                        'response': notebook_response,
                        'response_with_image': notebook_response_copy,
                        'prompt_files': ",".join([f.split('/')[-1] for f in prompt_files]),
                        'prompt_file_urls': ", ".join(prompt_file_urls),
                        'timestamp': datetime.now(),
                        **ERROR_COUNTS_DICT
                    })
                    ensure_directory_exists('time-tracksheet/')

                    df_filepath = 'time-tracksheet/gemini-prompts-time-track-sheet.xlsx'
                    append_to_excel(df_filepath, new_data)

                    # Update this task's row in the spreadsheet with prompt response
                    processor.update_task_row_data_in_tracker(
                        task_id, 
                        idx+1,
                        notebook_response, 
                    )

                # Instantiate class for generating notebook after all prompts are done
                ipynb_gen = IPYNBGenerator(
                    output_path = output_dir,
                    rater_id    = RATER_ID,
                    task_id     = task_id
                )

                # Generate notebook
                nb_name = ipynb_gen.text_to_notebook(
                    OUTPUT[task_id]
                )

                # Notebook generated. Upload the folder to Google Drive and get the notebook link
                notebook_links = processor.upload_folder(output_dir, task_id, RATER_ID, script_type="Gemini")
                print('nb_name:',nb_name)
                print('notebook_links:',notebook_links)
                if notebook_links:
                    # Update the task's row in the spreadsheet with the notebook google drive link
                    processor.update_gemini_colab_links_in_tracker(
                        task_id, 
                        notebook_links,
                        nb_name
                    )
                else:
                    print("Directory for task", task_id, "already exists in drive")
                    row_index = processor.get_task_row_index(task_id)
                    processor.sheet.update_cell(row_index, processor.sheet.find("GN8K Status").col, "Rater Added Query")

                print(f'[x] Completed Task ID: {task_id}.\n\n')

        except Exception as e:
            print('Error E',e)
            # In case of an error, set the status of the row back to "Rater added query"
            row_index = processor.get_task_row_index(task_id)
            processor.sheet.update_cell(row_index, processor.sheet.find("GN8K Status").col, "Rater Added Query")

    # Check if there is any new task
    tasks = processor.fetch_new_task()
    XON = True if len(tasks) > 0 else False
    print('New Task Found:', XON)




''' FOR GEMINI
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\selenium_chrome_profile"

/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="/Users/<your-username>/selenium_chrome_profile"

google-chrome --remote-debugging-port=9222 --user-data-dir="/home/<your-username>/selenium_chrome_profile"

'''