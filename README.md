# Automation Script for Running and Documenting Prompts v2.3.1

This project aims to automate the process of running and documenting the results of various prompts and storing them into notebooks. 

## Requirements

- Google Chrome version `125.0.6422.78` or higher

## Setup

1. Ensure Google Chrome is installed and up-to-date.
2. Start two Chrome sessions in debug mode using one of the commands below depending on your Operating System:

- ### Start Chrome Session For Gemini

    **Windows:**
    ```sh
    "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\selenium_chrome_profile"
    ```

    **macOS:**
    ```sh
    /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="/Users/<your-username>/selenium_chrome_profile"
    ```

    **Linux:**
    ```sh
    google-chrome --remote-debugging-port=9222 --user-data-dir="/home/<your-username>/selenium_chrome_profile"
    ```
- ### Start Chrome Session For ChatGPT

    **Windows:**
    ```sh
    "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9333 --user-data-dir="C:\selenium_chrome_profile_2"
    ```

    **macOS:**
    ```sh
    /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9333 --user-data-dir="/Users/<your-username>/selenium_chrome_profile_2"
    ```

    **Linux:**
    ```sh
    google-chrome --remote-debugging-port=9333 --user-data-dir="/home/<your-username>/selenium_chrome_profile_2"
    ```

3. Log into your Gemini account on the first chrome window.

4. Log into your ChatGPT account on the second chrome window.

5. Ensure you have the libraries in `requirements.txt` installed into your python environment.

6. Open 2 termninal sessions, navigate to the root project directory where the scripts `gemini.py` and `chatgpt.py` are located and run them separately in the 2 terminals.

**NOTE:** _Completely minimize mouse interactions to ensure a smooth process while the script is/are running as the script will mostly use the keyboard to type the file path when uploading files. If you're using the mouse elsewhere, the keyboard, will attempt to type the path of the file at wherever you focused the mouse instead of the web file input form popup. As it stands, both Gemini and GPT platforms don't make it possible to upload files using automated scripts, that's why I had to resort to the use of keyboard, in case you were wondering why. :)_

## Configuration

Create a `jobs.json` file in the script's directory with the structure below. You will be populating this file will your various prompts and file paths because these is where both `gemini.py` and `chatgpt.py` will be reading your inputs from:

```python
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
        },
        {
            "task_id": "101", # ID assigned to that row on google sheet
            # The script uploads all your files in the beginning of the chat.
            # So currently you won't be uploading different files per turn, all will be 
            # combined and uploaded at the very beginning of the chat session.
            "files": [
                {
                    "path": "relative_file_path_1",
                    "url": "https://url_of_file"
                },
                {
                    "path": "relative_file_path_2",
                    "url": "https://url_of_file"
                }
                # ...
            ],
            "prompts": [
                "User Prompt 1",
                "User Prompt 2",
                "User Prompt 3",
                # ...
            ]
        }
    ]
}
```

- **rater_id**: The unique number assigned to the rater.
- **tasks**: A list of dictionaries, each representing a task.
  - **task_id**: The ID number given to that task on the excel sheet.
  - **files**: A list of file names relative to the script directory.
  - **prompts**: A list of prompt strings. The first prompt should be entered first, followed by the second, and so on.

There can be an infinite number of tasks.

## Usage

Once Chrome is running in debug mode and you are logged into Gemini:

1. Place your `jobs.json` file in the script directory.
2. Run the script to start the automation process.

## Author

[Fred Dunyo](https://github.com/dunfred)

## Miscellaneous
1. Gemini Chrome Port: 9222
2. ChatGPT Chrome Port: 9333
