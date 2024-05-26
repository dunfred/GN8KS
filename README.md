# Automation Script for Running and Documenting Prompts

This project aims to automate the process of running and documenting the results of various prompts and storing them into notebooks. 

## Requirements

- Google Chrome version `125.0.6422.78` or higher

## Setup

1. Ensure Google Chrome is installed and up-to-date.
2. Start Chrome in debug mode using one of the commands below:

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

3. Log into your Gelmi platform.

4. Minimize mouse interactions to ensure a smooth process while the script is running.

## Configuration

Create a `jobs.json` file in the script directory with the following structure:

```json
{
    "rater_id": 000,
    "tasks": [
        {
            "task_id": "00",
            "files": [
                "relative_file_path_1",
                "relative_file_path_2",
                ...
            ],
            "prompts": [
                "User Prompt 1",
                "User Prompt 2",
                ...
            ]
        }
    ]
}
```

- **rater_id**: The unique ID of the user.
- **tasks**: A list of dictionaries, each representing a task.
  - **task_id**: A unique identifier for each task.
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
