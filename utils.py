import os
# import cairosvg
from PIL import Image
from io import BytesIO
import base64
from reportlab.graphics import renderPM
from svglib.svglib import svg2rlg
from selenium.webdriver.common.by import By

# Function to ensure the directory exists
def ensure_directory_exists(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

# Function to save SVG data to a PNG file using reportlab and Pillow
def save_svg_to_png(svg_data, file_path):
    drawing = svg2rlg(BytesIO(svg_data.encode('utf-8')))
    png_data = renderPM.drawToPIL(drawing)
    png_data.save(file_path)

# # Function to save SVG data to a PNG file
# def save_svg_to_png(svg_data, file_path):
#     cairosvg.svg2png(bytestring=svg_data.encode('utf-8'), write_to=file_path)

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
class SpecificTextInLastElement:
    def __init__(self, locator, text):
        self.locator = locator
        self.text = text

    def __call__(self, driver):
        elements = driver.find_elements(*self.locator)
        if elements:
            last_element = elements[-1]
            if self.text in last_element.text:
                return last_element
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

