import os
import sys
import re
import json
import glob
import shutil

SOURCE_DIR = '/content/extracted_meetings'
DRIVE_DB_DIR = '/content/drive/MyDrive/WindyCityMeetings/processed_database'
PUBLIC_DB_PATH = 'public/master_meetings_database_linked.json'

def run_build_pipeline():
    print("Starting automated rebuild for all transcripts...")
    # Load and map meeting markdown files
    md_files = glob.glob(os.path.join(SOURCE_DIR, '*.md'))
    print(f"Processing {len(md_files)} files...")
    
    # Clear out any old web cache and populate all 720 transcripts directly
    master_data = []
    for i, file_path in enumerate(md_files):
        filename = os.path.basename(file_path)
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        # Standard metadata
        match = re.search(r'(\d{1,2})[-_](\d{1,2})[-_](\d{2,4})', filename)
        date = "Unknown"
        if match:
            month, day, year = match.groups()
            if len(year) == 2:
                year = "20" + year
            date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            
        category = "Other/Supporting"
        lower_name = filename.lower()
        if "council" in lower_name:
            category = "City Council"
        elif "finance" in lower_name:
            category = "Finance Committee"
        elif "work_session" in lower_name or "work session" in lower_name:
            category = "Work Session"
        elif "public_services" in lower_name or "public services" in lower_name:
            category = "Public Services Committee"
        elif "planning" in lower_name:
            category = "Planning Commission"

        master_data.append({
            "id": f"meet_{i:04d}",
            "title": filename.replace(".md", "").replace("_", " "),
            "filename": filename,
            "date": date,
            "category": category,
            "turns": [{"speaker": "Context/Agenda", "text": line.strip()} for line in content.split('\n') if line.strip()][:50],
            "raw_text_length": len(content),
            "agendas": [],
            "minutes": [],
            "supporting_documents": []
        })
        
    # Ensure directories exist and save public database assets
    os.makedirs('public', exist_ok=True)
    with open(PUBLIC_DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(master_data, f, indent=2)
    print(f"Successfully wrote {len(master_data)} total transcripts directly to web output directory!")

if __name__ == '__main__':
    run_build_pipeline()
