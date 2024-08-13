import io
import os
import gspread
from dotenv import load_dotenv
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.http import MediaIoBaseDownload
from google.auth.transport.requests import AuthorizedSession

load_dotenv()

SHARED_FOLDER_ID = os.getenv("SHARED_FOLDER_ID")

SPREAD_SHEET_ID = os.getenv("SPREAD_SHEET_ID")

SERVICE_ACCOUNT_PATH = os.getenv("SERVICE_ACCOUNT_PATH")

class TaskProcessor:
    def __init__(self):
        # Set notebooks upload directory id
        self.raters_folder_id = SHARED_FOLDER_ID # "Comparative Analysis Generated Notebooks GN8Ks"

        # Initialize Google Sheets and Drive
        self.spreadsheet_id = SPREAD_SHEET_ID
        self.credentials_path = SERVICE_ACCOUNT_PATH

        scoped_credentials = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        self.creds = Credentials.from_service_account_file(self.credentials_path)
        self.scoped_creds = self.creds.with_scopes(scoped_credentials)

        self.gc = gspread.client.Client(self.scoped_creds)
        self.gc.session = AuthorizedSession(scoped_credentials)
        
        # Access "GN8K Tracker" worksheet
        self.sheet = self.gc.open_by_key(self.spreadsheet_id).sheet1 #.worksheet("GN8K Tracker")

        # Initialize Google Drive
        gauth = GoogleAuth()

        gauth.credentials = ServiceAccountCredentials.from_json_keyfile_name(
            SERVICE_ACCOUNT_PATH, 
            scopes=['https://www.googleapis.com/auth/drive']
        )

        # Initialize GoogleDrive instance
        self.drive = GoogleDrive(gauth)
        print(self.drive)

    def fetch_tasks(self, initial_status='Rater Added Query', script_type="Gemini"):
        """
        Fetches rows based on initial status or ready status with missing A Link or B Link.
        
        :param sheet: The Google Sheet object.
        :param initial_status: The initial status to filter rows.
        :param script_type: 'A' or 'B' to determine which script is running.
        :return: List of rows that need to be processed.
        """
        rows = self.sheet.get_all_records()
        filtered_rows = []

        # Status_to_check_for
        s_to_check = "GPT" if script_type == "Gemini" else "Gemini"

        # Determine the link column based on the script type
        link_column = f"{script_type} Response Colab"

        for row in rows:
            status = row['Status']
            link_value = str(row.get(link_column, "")).strip()
            if status == initial_status or \
                (status == "Ready For Rating" and not link_value) or\
                status == f"{s_to_check} Done {script_type} Pending":
                filtered_rows.append(row)

        return filtered_rows

    def get_or_create_folder(self, parent_folder_id, folder_name):
        # Query for the folder by name under the specified parent
        folder_list = self.drive.ListFile({
            'q': f"'{parent_folder_id}' in parents and title = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed=false"
        }).GetList()
        
        if folder_list:
            # If the folder exists, return the first match
            return folder_list[0]['id']
        else:
            # Folder doesn't exist, create it
            folder_metadata = {
                'title': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [{'id': parent_folder_id}]
            }
            folder = self.drive.CreateFile(folder_metadata)
            folder.Upload()
            return folder['id']

    def skip_existing_file_in_drive(self, folder_id, file_path):
        file_name = os.path.basename(file_path)
        
        # Search for the file with the same name in the folder
        file_list = self.drive.ListFile({
            'q': f"'{folder_id}' in parents and title = '{file_name}' and trashed=false"
        }).GetList()
        
        if file_list:
            # If the file exists, skip the upload
            print(f"File already exists: {file_name}, skipping upload.")
            return False
        else:
            # Upload the new file if it doesn't exist
            file_drive = self.drive.CreateFile({'title': file_name, 'parents': [{'id': folder_id}]})
            file_drive.SetContentFile(file_path)
            file_drive.Upload()
            print(f"Uploaded new file: {file_name} to Google Drive folder.")
            return True

    def upload_folder(self, local_folder_path, task_id, rater_id, script_type="Gemini"):
        # Get or create the folder
        folder_id = self.get_or_create_folder(self.raters_folder_id, task_id)

        notebook_links = {'Gemini': None, 'GPT': None}

        # Upload all files in the local folder to this new Drive folder
        for filename in os.listdir(local_folder_path):
            # Search for the file with the same name in the folder
            file_list = self.drive.ListFile({
                'q': f"'{folder_id}' in parents and title = '{filename}' and trashed=false"
            }).GetList()
            
            if file_list:
                # If the file exists, skip the upload
                print(f"File already exists: {filename}, skipping upload.")
            else:
                if str(script_type).lower() in str(filename).lower():
                    # Upload the new file if it doesn't exist
                    file_path = os.path.join(local_folder_path, filename)
                    file_drive = self.drive.CreateFile({
                        'title': filename,
                        'parents': [{'id': folder_id}]
                    })
                    file_drive.SetContentFile(file_path)
                    file_drive.Upload()

                    # Check if the file is one of the notebooks and store its link
                    if filename == f"Gemini_rater_{rater_id}_ID_{task_id}.ipynb":
                        notebook_links['Gemini'] = file_drive['alternateLink']

                    elif filename == f"GPT_rater_{rater_id}_ID_{task_id}.ipynb":
                        notebook_links['GPT'] = file_drive['alternateLink']

        return notebook_links

    def update_task_row_data_in_tracker(self, task_id, prompt_index, prompt_response):
        # Find the row index by TASK_ID and update it
        row_index = self.get_task_row_index(task_id)
        # Get the column index based on the custom column name
        col_index = self.get_column_index_by_name(f"Gemini Response \nTurn {prompt_index}")
        # Update the cell styling
        cell_reference = gspread.utils.rowcol_to_a1(row_index, col_index)
        # Clip the text to prevent resizing
        self.sheet.format(cell_reference, {"wrapStrategy": "CLIP"})
        # Set fixed row height after updating content to ensure the height is unaffected
        self.set_row_height(row_index, 20)

        # Now add cell values
        self.sheet.update_cell(row_index, self.sheet.find(f"Gemini Response \nTurn {prompt_index}").col, prompt_response)

    def update_gemini_colab_links_in_tracker(self, task_id, notebook_links, notebook_name):
        # Find the row index by TASK_ID and update it
        row_index = self.get_task_row_index(task_id)
        
        if notebook_links['Gemini']:
            file_link = notebook_links['Gemini']
            gemini_file = f'=HYPERLINK("{file_link}", "{notebook_name}")'

            # Get the column index based on the custom column name
            col_index = self.get_column_index_by_name("Gemini Response Colab")
            # Update the cell styling
            cell_reference = gspread.utils.rowcol_to_a1(row_index, col_index)
            # Clip the text to prevent resizing
            self.sheet.format(cell_reference, {"wrapStrategy": "CLIP"})
            # Set fixed row height after updating content to ensure the height is unaffected
            self.set_row_height(row_index, 20)

            # Now add cell value
            self.sheet.update_cell(row_index, self.sheet.find("Gemini Response Colab").col, gemini_file)
            
            if self.check_if_notebook_link_exists(task_id, "GPT"):
                # If GPT notebook link exists, then it means this row is done
                self.sheet.update_cell(row_index, self.sheet.find("Status").col, "Ready For Rating")
            else:
                # Otherwise set the status to show that GPT notebook is yet to be added
                self.sheet.update_cell(row_index, self.sheet.find("Status").col, "Gemini Done GPT Pending")

    def update_gpt_colab_links_in_tracker(self, task_id, notebook_links, notebook_name):
        # Find the row index by TASK_ID and update it
        row_index = self.get_task_row_index(task_id)

        if notebook_links['GPT']:
            file_link = notebook_links['GPT']
            gpt_file = f'=HYPERLINK("{file_link}", "{notebook_name}")'

            # Get the column index based on the custom column name
            col_index = self.get_column_index_by_name("GPT Response Colab")
            # Update the cell styling
            cell_reference = gspread.utils.rowcol_to_a1(row_index, col_index)
            # Clip the text to prevent resizing
            self.sheet.format(cell_reference, {"wrapStrategy": "CLIP"})
            # Set fixed row height after updating content to ensure the height is unaffected
            self.set_row_height(row_index, 20)

            # Now add cell value
            self.sheet.update_cell(row_index, self.sheet.find("GPT Response Colab").col, gpt_file)

            if self.check_if_notebook_link_exists(task_id, "Gemini"):
                # Igf Gemini notebook link exists, then it means this row is done
                self.sheet.update_cell(row_index, self.sheet.find("Status").col, "Ready For Rating")
            else:
                # Otherwise set the status to show that Gemini notebook is yet to be added
                self.sheet.update_cell(row_index, self.sheet.find("Status").col, "GPT Done Gemini Pending")

    def get_task_row_index(self, task_id):
        # Find the row index by TASK_ID and update it
        rows = self.sheet.get_all_records()
        for idx, row in enumerate(rows):
            if row['TASK_ID'] == task_id:
                row_index = idx + 2  # +2 accounts for header row and zero-indexing
                return row_index
        return None

    def check_if_notebook_link_exists(self, task_id, script_name):
        # Find the row index by TASK_ID and update it
        rows = self.sheet.get_all_records()
        for idx, row in enumerate(rows):
            if row['TASK_ID'] == task_id:
                # Check if notebook link exists for script type and it's a url

                # if 'https://' in str(row.get(f"{script_name} Response Colab", "")).strip():
                if str(row.get(f"{script_name} Response Colab", "")).strip():
                    return True
                return False
        return False

    # Function to get the column index based on the custom column name
    def get_column_index_by_name(self, custom_col_name):
        # Get the first row which contains the headers
        headers = self.sheet.row_values(1)
        
        if custom_col_name in headers:
            # Column index is 1-based; gspread uses 1-based indexing
            return headers.index(custom_col_name) + 1
        else:
            raise ValueError(f"Column name '{custom_col_name}' not found in headers.")

    # Function to get the file name and check if it exists locally
    def get_file_name_from_drive_link_and_download(self, file_url, local_dir='query_files'):
        # Extract the file ID from the URL
        file_id = file_url.split('/d/')[1].split('/')[0]

        # Get the file metadata and name
        file = self.drive.CreateFile({'id': file_id})
        file.FetchMetadata(fields='title,labels,mimeType')
        file_name = file['title']
        print('File Name:', file_name)
        print('Mime type',file['mimeType'])

        # Ensure the local directory exists
        if not os.path.exists(local_dir):
            os.makedirs(local_dir)

        # Check if the file already exists locally
        local_file_path = os.path.join(local_dir, file_name)
        if os.path.exists(local_file_path):
            print(f"File '{file_name}' exists locally at: {local_file_path}")
            return local_file_path.replace('\\', '/')

        # Download the file to the local directory
        try:
            file.GetContentFile(local_file_path)
            print(f"File downloaded to: {local_file_path}")
            return local_file_path
        except Exception as e:
            print(f"Failed to download file: {e}")
            return None

    # Simplified function to set row height
    def set_row_height(self, row_number, height):
        sheet_id = self.sheet._properties['sheetId']
        body = {
            "requests": [
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": row_number - 1,  # 0-based index
                            "endIndex": row_number
                        },
                        "properties": {
                            "pixelSize": height
                        },
                        "fields": "pixelSize"
                    }
                }
            ]
        }
        self.sheet.spreadsheet.batch_update(body)

