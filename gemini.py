import base64
from datetime import datetime
import os
import time
import json
import random
import pyperclip
import platform
import pandas as pd
from pathlib import Path
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
from utils import LastFooterElement, TextInLastElement, GeminiSpecificTextInLastElement, append_to_excel, ensure_directory_exists, update_prompt_output

''' SAMPLE `jobs.json` file template
{
    "rater_id": "000", # Your unique rater id
    "tasks": [
        {
            "task_id": "100", # ID assigned to that row on google sheet
            # The script uploads all your files in the beginning of the chat.
            # So currently you won't be uploading different files per turn, all will be 
            # combined and uploaded at the very beginning of the chat session.
            "files": [
                {
                    "path": "relative_file_path_1",
                    "url": "https://url_of_file"
                },
                # ...
            ],
            "prompts": [
                "User Prompt 1",
                "User Prompt 2",
                
                # ...
            ]
        }
    ]
}
'''

try:
    with open('jobs.json', 'r') as jfp:
        JOBS = json.loads(jfp.read())
except FileNotFoundError:
    JOBS = {}
    raise('Please make sure you "jobs.json" file is added to this directory before proceeding!')
except json.decoder.JSONDecodeError:
    JOBS = {}
    raise('Your "jobs.json" file has syntax some issues, kindly fix them before proceeding.')

pprint(JOBS)

try:
    with open('gemini-outputs.json', 'r') as of:
        OUTPUT = defaultdict(list, json.loads(of.read()))  # Convert to defaultdict type
except Exception:
    OUTPUT = defaultdict(list)

RATER_ID = JOBS['rater_id']

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


# Initialize WebDriver with the appropriate ChromeDriver
chromedriver_path = get_chromedriver_path()
print('Chrome Driver Path:', chromedriver_path)

# Configure Chrome options
options = Options()
options.add_experimental_option("debuggerAddress", "localhost:9222") # Your Gemini's chrome profile port would be on port "9222"
options.add_argument("--disable-blink-features=AutomationControlled")

# Function to introduce random delays
def random_delay(a=2, b=5):
    time.sleep(random.uniform(a, b))

# Initialize WebDriver with the appropriate ChromeDriver
service = ChromeService(executable_path=chromedriver_path)
driver = webdriver.Chrome(service=service, options=options)


# Open a new session and run all prompts for each task/job
for task in JOBS['tasks']:
    task_id           = task['task_id']
    prompt_files      = [f['path'] for f in task['files']]
    prompt_file_urls = [f.get('url', "") for f in task['files']]

    files_uploaded = False

    if task['prompts']: # Continue if prompts are available
        # Ensure the output directory exists
        base_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(base_dir, 'notebooks', f"ID_{task_id}")
        ensure_directory_exists(output_dir)

        print(f'[x] Started Task ID: {task_id}.')

        # Open Gemini
        driver.get('https://gemini.google.com/')

        try:
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.TAG_NAME, 'bard-sidenav-content')))
            main_container_tag_name = 'bard'
        except Exception:
            main_container_tag_name = 'mat'

        for idx, user_query in enumerate(task['prompts']):
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
                    if is_first_file:
                        upload_files_elem_xpath = f'//*[@id="app-root"]/main/side-navigation-v2/{main_container_tag_name}-sidenav-container/{main_container_tag_name}-sidenav-content/div/div/div[2]/chat-window/div[1]/div[2]/div[1]/input-area-v2/div/div/div[3]/div/uploader/div[1]/div/button'
                    else:
                        upload_files_elem_xpath = f'//*[@id="app-root"]/main/side-navigation-v2/{main_container_tag_name}-sidenav-container/{main_container_tag_name}-sidenav-content/div/div/div[2]/chat-window/div[1]/div[2]/div[1]/input-area-v2/div/div/div[4]/div/uploader/div[1]/div/button'
                    
                    WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, upload_files_elem_xpath)))
                    
                    driver.find_element(By.XPATH, upload_files_elem_xpath).click()

                    upload_local_file_xpath = '//*[@id="file-uploader-local"]'
                    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, upload_local_file_xpath)))
                    local_file_input = driver.find_element(By.XPATH, upload_local_file_xpath)
                    local_file_input.click() 
                    time.sleep(3)
                    keyboard = Controller()
                    keyboard.type(file)
                    keyboard.press(PyKey.enter)
                    keyboard.release(PyKey.enter)
                    is_first_file = False
                    print(f'[x] Prompt {idx+1}: File Uploaded Successfully! - {file}')
                # Make sure script doesn't attempt to upload files again.
                files_uploaded = True
                time.sleep(3)

            # Submit the query.
            submit_prompt_btn_xpath = f'//*[@id="app-root"]/main/side-navigation-v2/{main_container_tag_name}-sidenav-container/{main_container_tag_name}-sidenav-content/div/div/div[2]/chat-window/div[1]/div[2]/div[1]/input-area-v2/div/div/div[4]/div/div/button'

            time.sleep(3)
            try:
                WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, submit_prompt_btn_xpath)))
            except Exception:
                submit_prompt_btn_xpath = f'//*[@id="app-root"]/main/side-navigation-v2/{main_container_tag_name}-sidenav-container/{main_container_tag_name}-sidenav-content/div/div/div[2]/chat-window/div[1]/div[2]/div[1]/input-area-v2/div/div/div[3]/div/div/button'
                try:
                    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, submit_prompt_btn_xpath)))
                except Exception:
                    submit_prompt_btn_xpath = f'//*[@id="app-root"]/main/side-navigation-v2/{main_container_tag_name}-sidenav-container/{main_container_tag_name}-sidenav-content/div/div[2]/chat-window/div[1]/div[2]/div[1]/input-area-v2/div/div/div[1]/div/div[1]/rich-textarea/div[1]'
                    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, submit_prompt_btn_xpath)))

            submit_prompt_btn = driver.find_element(By.XPATH, submit_prompt_btn_xpath)
            submit_prompt_btn.click()

            # Define the locator for the element you want to observe
            observed_element_locator = (By.CSS_SELECTOR, "[class^='response-container-content']")
            start_time_to_trigger_ice = time.time()

            # Wait for the element to be present
            WebDriverWait(driver, 60).until(EC.presence_of_element_located(observed_element_locator))

            # Wait for the text "Analyzing..." to appear in the element or its nested elements
            WebDriverWait(driver, 210).until(TextInLastElement(observed_element_locator))

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
            response_footer_element = WebDriverWait(driver, 210).until(LastFooterElement(observed_element_locator, "response-container-footer"))
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
                more_options_menu_element_xpath = './/*[@aria-label="Show more options" and @mattooltip="More" and contains(@class, "mat-mdc-menu-trigger")]'
                WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, more_options_menu_element_xpath)))

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

            # Update the local backup data with latest prompt data if already exists, else add as new
            update_prompt_output(
                main_dict       = OUTPUT,
                id_key          = task_id,
                new_prompt_dict =   {
                    'prompt': user_query,
                    'time_to_ice': time_to_trigger_ice,
                    'end_to_end_time': end_to_end_time,
                    'response': notebook_response,
                    'prompt_files': prompt_files,
                    'prompt_file_urls': prompt_file_urls,
                    'timestamp': str(datetime.now())
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
                'prompt_files': ",".join([f.split('/')[-1] for f in prompt_files]),
                'prompt_file_urls': ", ".join(prompt_file_urls),
                'timestamp': datetime.now()
            })
            ensure_directory_exists('time-tracksheet/')

            df_filepath = 'time-tracksheet/gemini-prompts-time-track-sheet.xlsx'
            append_to_excel(df_filepath, new_data)


        # Instantiate class for generating notebook after all prompts are done
        ipynb_gen = IPYNBGenerator(
            output_path = output_dir,
            rater_id    = RATER_ID,
            task_id     = task_id
        )

        # Generate notebook
        ipynb_gen.text_to_notebook(
            OUTPUT[task_id]
        )
        print(f'[x] Completed Task ID: {task_id}.\n\n')







''' FOR GEMINI
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\selenium_chrome_profile"

/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="/Users/<your-username>/selenium_chrome_profile"

google-chrome --remote-debugging-port=9222 --user-data-dir="/home/<your-username>/selenium_chrome_profile"

'''