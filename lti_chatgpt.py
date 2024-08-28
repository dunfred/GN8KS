''' This tool fetches queries from the Gemini vs GPT Comparative tracker, generates the notebooks and updates tracker
'''

import base64
import os
import time
import json
import random
import platform
import bs4
from bs4 import BeautifulSoup
import pyautogui
import requests
import pandas as pd
from pathlib import Path
from pprint import pprint
from datetime import datetime
from selenium import webdriver
from collections import defaultdict
from bake_notebook import IPYNBGenerator
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from pynput.keyboard import Key as PyKey, Controller
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from process_and_update_tracker import TaskProcessor
from utils import GPTSpecificTextInLastElement, append_to_excel, ensure_directory_exists, update_prompt_output


OUTPUT = defaultdict(list)

print(platform.system())
print(platform.machine())

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
options.add_argument("--disable-gpu")  # This option is recommended to avoid hardware acceleration issues
options.add_argument("--window-size=1920,1080")  # You can specify your desired window size
options.add_argument('--no-sandbox')

if system != "Darwin":
    # Path to your existing user profile
    if system == "Windows":
        options.add_argument(r'--user-data-dir=C:\selenium_chrome_profile_2')

    elif system == "Darwin":
        options.add_argument(f'--user-data-dir=/Users/{system_username}/selenium_chrome_profile_2')

    elif system == "Linux":
        options.add_argument(f'--user-data-dir=/home/{system_username}/selenium_chrome_profile_2')

    else:
        raise Exception("Unsupported operating system")
else:
    options.add_experimental_option("debuggerAddress", "localhost:9333") # Your GPT's chrome profile port would be on port "9333"

options.add_argument("--disable-blink-features=AutomationControlled")

# Function to introduce random delays
def random_delay(a=2, b=5):
    time.sleep(random.uniform(a, b))

# Initialize WebDriver with the appropriate ChromeDriver
service = ChromeService(executable_path=chromedriver_path)
driver = webdriver.Chrome(service=service, options=options)

# Get the screen size
screen_width = driver.execute_script("return screen.width;")
screen_height = driver.execute_script("return screen.height;")

# Calculate the window size and position
window_width = int(screen_width * 0.8) if int(screen_width * 0.8) < 1180 else 1180
window_height = screen_height if screen_height < 1080 else 1080
# window_x = screen_width - window_width  # Align to the right
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
tasks = processor.fetch_new_task(script_type="GPT")

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

                # # Set the status of the tracker row to indicate it's been worked on
                # row_index = processor.get_task_row_index(task_id)
                # processor.sheet.update_cell(row_index, processor.sheet.find("GN8K Status").col, "Tool In Progress")

                # Open GPT
                driver.get('https://chatgpt.com/?model=gpt-4o')

                for idx, user_query in enumerate(TASK_PROMPTS):
                    print(f'[x] {task_id} - Starting Prompt {idx+1}: {user_query}')
                    # Find the input text field elem
                    input_text_elem_xpath = '//*[@id="prompt-textarea"]'
                    WebDriverWait(driver, 120).until(EC.presence_of_element_located((By.XPATH, input_text_elem_xpath)))

                    # Generate full path to all prompt files
                    files_str = list(map(lambda x: str(Path(x).resolve()), prompt_files))
                    time.sleep(3)
                    prompt_elem = driver.find_element(By.XPATH, input_text_elem_xpath)

                    # Assuming some prompts have new lines
                    # Split the text into lines
                    lines = user_query.split('\n')

                    # Send each line separately followed by SHIFT+ENTER to create a new line without triggering the form submission
                    for line in lines:
                        prompt_elem.send_keys(line)
                        prompt_elem.send_keys(Keys.SHIFT + Keys.ENTER)

                    # Find the file input element by its name or ID
                    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, input_text_elem_xpath)))

                    # Ensures all files are uploaded just once.
                    if not files_uploaded:
                        for file in files_str:
                            try:
                                upload_files_elem_xpath = "//*[starts-with(@id, 'radix-:r')]/following-sibling::button[@aria-label='Attach files'][1]"
                                WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, upload_files_elem_xpath)))
                            except Exception:
                                try:
                                    upload_files_elem_xpath = '//*[@id="__next"]/div[1]/div[2]/main/div[1]/div[2]/div[1]/div/form/div/div[2]/div/div/div[1]/span/div/button[2]'
                                    WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, upload_files_elem_xpath)))
                                except Exception:
                                    upload_files_elem_xpath = '//*[@id="__next"]/div[1]/div[2]/main/div[1]/div[2]/div[1]/div/form/div/div[2]/div/div/div[1]/div/button[2]'
                                    WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, upload_files_elem_xpath)))

                            driver.find_element(By.XPATH, upload_files_elem_xpath).click()

                            # Construct the XPath to find the upload file element with this id prefix and text match
                            upload_local_file_xpath = '//*[starts-with(@id, "radix-:r")]/div[4][text()="Upload from computer"]'

                            try:
                                WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, upload_local_file_xpath)))
                            except Exception:
                                upload_local_file_xpath = '//*[starts-with(@id, "radix-:r")]/div[3][text()="Upload from computer"]'
                                WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, upload_local_file_xpath)))

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
                                
                            print(f'[x] Prompt {idx+1}: File Uploaded Successfully! - {file}')

                        # Make sure script doesn't attempt to upload files again.
                        files_uploaded = True
                        time.sleep(5)
                        # time.sleep(20)

                    # Submit the query.
                    try:
                        submit_prompt_btn_xpath = "//button[@aria-label='Send prompt' and @data-testid='send-button']"
                        WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, submit_prompt_btn_xpath)))
                    except Exception:
                        submit_prompt_btn_xpath = '//*[@id="__next"]/div[1]/div[2]/main/div[1]/div[2]/div[1]/div/form/div/div[2]/div/div/button'
                        WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, submit_prompt_btn_xpath)))

                    submit_prompt_btn = driver.find_element(By.XPATH, submit_prompt_btn_xpath)
                    try:
                        submit_prompt_btn.click()
                    except Exception:
                        time.sleep(30) # Wait 30 more seconds and try again
                        submit_prompt_btn = driver.find_element(By.XPATH, submit_prompt_btn_xpath)
                        submit_prompt_btn.click()

                    # Define the locator for the element you want to observe
                    observed_element_locator = (By.CSS_SELECTOR, '[class*="group/conversation-turn"][class*="agent-turn"]')
                    start_time = time.time()

                    # Wait for the element to be present
                    WebDriverWait(driver, 30).until(EC.presence_of_element_located(observed_element_locator))

                    # Continue to wait for the specific text "Analyzed"
                    WebDriverWait(driver, 180).until(GPTSpecificTextInLastElement(
                        observed_element_locator, 
                        "Analyzed", 
                        idx+1,
                        turn_menu_item_locator = (By.XPATH, './/div[contains(@class, "mt-1") and contains(@class, "flex") and contains(@class, "gap-3") and contains(@class, "empty:hidden") and contains(@class, "ml-")]')
                        ))

                    # Record the time when "Analyzed" appears
                    analysis_complete_time = time.time()
                    end_to_end_time = round(analysis_complete_time - start_time, 2)
                    print(f"[x] Prompt {idx+1} End To End Time: {end_to_end_time} seconds")

                    elements = driver.find_elements(*observed_element_locator)
                    if elements:
                        gpt_reponse_elem = elements[-1]
                    else:
                        gpt_reponse_elem = None

                    # Ensure the bot is truly done with analysis by looking for the 
                    # action menu that every completed conversation has at the bottom
                    turn_menu_item_locator = (By.XPATH, './/div[contains(@class, "mt-1") and contains(@class, "flex") and contains(@class, "gap-3") and contains(@class, "empty:hidden") and contains(@class, "ml-")]')
                    WebDriverWait(gpt_reponse_elem, 180).until(EC.presence_of_element_located(turn_menu_item_locator))

                    # Grab all GPT code and text response blocks while maintaining order
                    response_blocks = gpt_reponse_elem.find_elements(By.XPATH, './/div[(normalize-space(@class) = "overflow-hidden") or @data-message-author-role="assistant"]')
                    # Sort in the order they appear on screen
                    response_blocks = sorted(response_blocks, key=lambda x: x.location['y'])

                    # Find all img elements within the response element that have the ngcontent attribute
                    plot_images = gpt_reponse_elem.find_elements(By.TAG_NAME, 'img')
                    plot_images = [i for i in plot_images if str(i.get_attribute('alt')).lower().strip() == "output image"]
                    base64_plot_images = []

                    if plot_images:
                        # Iterate through each plot image and save it
                        for img_idx, img in enumerate(plot_images):
                            # Get the src attribute, which contains the base64 encoded image
                            src = img.get_attribute('src')

                            # Download the image
                            response = requests.get(src)

                            file_path = os.path.join(output_dir, f'GPT_userquery{idx+1}_plot{img_idx+1}.png')

                            # Save the image to the specified path
                            with open(file_path, 'wb') as file:
                                file.write(response.content)
                                base64_plot_images.append(base64.b64encode(response.content).decode('utf-8'))

                        time.sleep(3)
                    else:
                        plot_images = gpt_reponse_elem.find_elements(By.XPATH, '''
                            .//div[
                                @class = "mb-3 max-w-[80%]"
                            ]
                        ''')
                        print('[x] Found', len(plot_images), 'Image' if len(plot_images) ==1 else 'Images')

                        if plot_images:
                            for img_idx, img in enumerate(plot_images):
                                file_path = os.path.join(output_dir, f'GPT_userquery{idx+1}_plot{img_idx+1}.png')
                                # Scroll the element into view using JavaScript
                                driver.execute_script("arguments[0].scrollIntoView(true);", img)

                                # Wait for the element to be fully visible
                                WebDriverWait(driver, 10).until(EC.visibility_of(img))
                                print('[x] Waiting for 5 seconds before snapping plot image')
                                time.sleep(5)
                                img.screenshot(file_path)

                                with open(file_path, 'rb') as imgfile:
                                    base64_plot_images.append(base64.b64encode(imgfile.read()).decode('utf-8'))
                            time.sleep(3)

                    # Create a combined list of elements and images, including the order they appear
                    all_elements = []
                    element_positions = [(element, element.location['y']) for element in response_blocks]
                    image_positions = [(image, image.location['y']) for image in plot_images]

                    # Combine and sort by vertical position (y-coordinate)
                    combined_positions = sorted(element_positions + image_positions, key=lambda x: x[1])

                    for item, _ in combined_positions:
                        if item.tag_name == 'img' or "mb-3 max-w-[80%]" in item.get_attribute('class'):
                            soup = BeautifulSoup('', 'html.parser')
                            # Create an img tag
                            img_tag = soup.new_tag('img', src=base64_plot_images[plot_images.index(item)])

                            all_elements.append(img_tag)
                        else:
                            # Get the outer HTML of the element to preserve its structure
                            all_elements.append(item)

                    # Create and cleanup notebook string
                    html_str = """"""
                    for blk in all_elements:
                        if isinstance(blk, bs4.element.Tag):
                            html_str += '\n' + str(blk)
                        else:
                            html_str += '\n' + blk.get_attribute('innerHTML')

                    update_prompt_output(
                        main_dict       = OUTPUT,
                        id_key          = task_id,
                        new_prompt_dict =   {
                            'prompt': user_query,
                            'end_to_end_time': end_to_end_time,
                            'html_response': html_str,
                            'prompt_files': prompt_files,
                            'prompt_file_urls': prompt_file_urls,
                            'timestamp': str(datetime.now())
                        }
                    )
                    
                    # Create local update/backup
                    with open('lti-gpt-outputs.json', 'w') as out:
                        out.write(json.dumps(OUTPUT))

                    new_data = pd.Series({
                        'rater_id': RATER_ID,
                        'task_id': task_id,
                        'prompt': user_query,
                        'time_to_ice': 0,
                        'end_to_end_time': end_to_end_time,
                        'prompt_files': ",".join([f.split('/')[-1] for f in prompt_files]),
                        'prompt_file_urls': ", ".join(prompt_file_urls),
                        'timestamp': datetime.now()
                    })
                    
                    ensure_directory_exists('time-tracksheet/')
                    df_filepath = 'time-tracksheet/gpt-prompts-time-track-sheet.xlsx'
                    append_to_excel(df_filepath, new_data)

                # To avoid getting logged out once in a while due to security reasons,
                # Will intentionally wait for a few more seconds before moving to next task 
                time.sleep(8)

                # Instantiate class for generating notebook after all prompts are done
                ipynb_gen = IPYNBGenerator(
                    output_path = output_dir,
                    rater_id    = RATER_ID,
                    task_id     = task_id,
                    nb_for="GPT" # Need to override this from "Gemini" to "GPT"
                )

                # Generate notebook
                nb_name = ipynb_gen.html_to_notebook(
                    OUTPUT[task_id]
                )

                # Notebook generated. Upload the folder to Google Drive and get the notebook link
                notebook_links = processor.upload_folder(output_dir, task_id, RATER_ID, script_type="GPT")
                print('nb_name:',nb_name)
                print('notebook_links:',notebook_links)
                if notebook_links:
                    # Update the task's row in the spreadsheet with the notebook google drive link
                    processor.update_gpt_colab_links_in_tracker(
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
    tasks = processor.fetch_new_task(script_type="GPT")
    XON = True if len(tasks) > 0 else False
    print('New Task Found:', XON)


''' FOR CHATGPT
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9333 --user-data-dir="C:\selenium_chrome_profile_2"

/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9333 --user-data-dir="/Users/<your-username>/selenium_chrome_profile_2"

google-chrome --remote-debugging-port=9333 --user-data-dir="/home/<your-username>/selenium_chrome_profile_2"

'''