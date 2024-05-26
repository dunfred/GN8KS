import os
import time
import json
import random
import pyperclip
import platform
from pathlib import Path
from selenium import webdriver
from collections import defaultdict
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service as ChromeService
from pynput.keyboard import Key as PyKey, Controller

from dotenv import load_dotenv
from pprint import pprint

from utils import LastFooterElement, TextInLastElement, SpecificTextInLastElement, ensure_directory_exists, save_svg_to_png


# Load environment variables from .env file
load_dotenv()

with open('jobs.json', 'r') as jfp:
    JOBS = json.loads(jfp.read())

pprint(JOBS)

OUTPUT = defaultdict(list)

RATER_ID = JOBS['rater_id']

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
    task_id        = task['task_id']
    prompt_files   = task['files']
    files_uploaded = False

    # Ensure the output directory exists
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, 'notebooks', f"{task_id}")
    ensure_directory_exists(output_dir)

    print(f'[x] Started Task ID: {task_id}.')

    # Open Gemini
    driver.get('https://gemini.google.com/')

    for idx, user_query in enumerate(task['prompts']):
        print(f'[x] {task_id} - Starting Prompt {idx+1}: {user_query}')
        # Find the input text field elem
        input_text_elem_xpath = '//*[@id="app-root"]/main/side-navigation-v2/bard-sidenav-container/bard-sidenav-content/div/div/div[2]/chat-window/div[1]/div[2]/div[1]/input-area-v2/div/div/div[1]/div/div[1]/rich-textarea/div[1]'
        WebDriverWait(driver, 120).until(EC.presence_of_element_located((By.XPATH, input_text_elem_xpath)))

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
                    upload_files_elem_xpath = '//*[@id="app-root"]/main/side-navigation-v2/bard-sidenav-container/bard-sidenav-content/div/div/div[2]/chat-window/div[1]/div[2]/div[1]/input-area-v2/div/div/div[3]/div/uploader/div[1]/div/button'
                else:
                    upload_files_elem_xpath = '//*[@id="app-root"]/main/side-navigation-v2/bard-sidenav-container/bard-sidenav-content/div/div/div[2]/chat-window/div[1]/div[2]/div[1]/input-area-v2/div/div/div[4]/div/uploader/div[1]/div/button'
                
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
        submit_prompt_btn_xpath = '//*[@id="app-root"]/main/side-navigation-v2/bard-sidenav-container/bard-sidenav-content/div/div/div[2]/chat-window/div[1]/div[2]/div[1]/input-area-v2/div/div/div[4]/div/div/button'

        try:
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, submit_prompt_btn_xpath)))
        except Exception:
            submit_prompt_btn_xpath = '//*[@id="app-root"]/main/side-navigation-v2/bard-sidenav-container/bard-sidenav-content/div/div/div[2]/chat-window/div[1]/div[2]/div[1]/input-area-v2/div/div/div[3]/div/div/button'
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, submit_prompt_btn_xpath)))

        submit_prompt_btn = driver.find_element(By.XPATH, submit_prompt_btn_xpath)
        submit_prompt_btn.click()

        # Define the locator for the element you want to observe
        observed_element_locator = (By.CSS_SELECTOR, "[class^='response-container-content']")
        start_time_to_trigger_ice = time.time()

        # Wait for the element to be present
        WebDriverWait(driver, 30).until(EC.presence_of_element_located(observed_element_locator))

        # Wait for the text "Analyzing..." to appear in the element or its nested elements
        WebDriverWait(driver, 60).until(TextInLastElement(observed_element_locator))

        # End timing
        end_time_to_trigger_ice = time.time()

        # Calculate the elapsed time
        time_to_trigger_ice = round(end_time_to_trigger_ice - start_time_to_trigger_ice, 2)
        print(f"[x] Prompt {idx+1} Time To Trigger ICE: {time_to_trigger_ice} seconds")

        # Continue to wait for the specific text "Analysis complete"
        WebDriverWait(driver, 600).until(SpecificTextInLastElement(observed_element_locator, "Analysis complete"))

        # Record the time when "Analysis complete" appears
        analysis_complete_time = time.time()
        end_to_end_time = round(analysis_complete_time - start_time_to_trigger_ice, 2)
        print(f"[x] Prompt {idx+1} End To End Time: {end_to_end_time} seconds")

        elements = driver.find_elements(*observed_element_locator)
        if elements:
            gemini_reponse_elem = elements[-1]
        else:
            gemini_reponse_elem = None

        # print('GEMINI RESPONSE ELEM:', gemini_reponse_elem)

        # Define the locator for the footer elements
        response_footer_locator = (By.XPATH, "following-sibling::div[contains(@class, 'response-container-footer')]")

        # Wait for the last footer element to be present
        response_footer_element = WebDriverWait(driver, 60).until(LastFooterElement(observed_element_locator, "response-container-footer"))
        # print("RESPONSE FOOTER ELEM:", response_footer_element)

        # Finding and clicking menu action bar to show copy button
        WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, ".//message-actions/div/div/div[2]/button")))
        more_options_menu = response_footer_element.find_element(By.XPATH, ".//message-actions/div/div/div[2]/button")
        more_options_menu.click()

        # Finding and clicking the actual copy button
        copy_response_xpath = "//*[contains(@id, 'mat-menu-panel-')]/div/div/button"
        WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, copy_response_xpath)))
        copy_response_button = response_footer_element.find_element(By.XPATH, copy_response_xpath)
        copy_response_button.click()

        # Find all SVG elements within the response container
        svg_elements = gemini_reponse_elem.find_elements(By.TAG_NAME, 'svg')

        # Save each SVG element as a PNG file in the order they appear
        for index, svg_element in enumerate(svg_elements):
            svg_data = svg_element.get_attribute('outerHTML')
            file_path = os.path.join(output_dir, f'svg_{index + 1}.png')
            save_svg_to_png(svg_data, file_path)
            print(f'[x] Saved Prompt {idx+1} plot to path: {file_path}')

        time.sleep(3)

        OUTPUT[task_id].append({
            'prompt': user_query,
            'time_to_ice': time_to_trigger_ice,
            'end_to_end_time': end_to_end_time,
            'response': pyperclip.paste()
        })

        with open('outputs.json', 'a') as out:
            out.write(json.dumps(OUTPUT))
















'''
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\selenium_chrome_profile"

/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="/Users/<your-username>/selenium_chrome_profile"

google-chrome --remote-debugging-port=9222 --user-data-dir="/home/<your-username>/selenium_chrome_profile"

'''