# modules/storage.py

import json
import os

STORAGE_DIR = "workflows_data"
PROJECTS_DIR = "projects_data"  # Directory for projects

def ensure_storage_dir():
    if not os.path.exists(PROJECTS_DIR):
        os.makedirs(PROJECTS_DIR)

def save_project(project_id, data):
    """
    Saves the project data to a JSON file with proper encoding.
    """
    path = os.path.join(PROJECTS_DIR, f"{project_id}.json")  # Changed from STORAGE_DIR to PROJECTS_DIR
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)



def load_project(project_id):
    """
    Loads the entire project, including nested workflows and common variable names, from a JSON file.
    """
    file_path = os.path.join(PROJECTS_DIR, f"{project_id}.json")
    if not os.path.exists(file_path):
        return None
    with open(file_path, "r") as f:
        return json.load(f)
