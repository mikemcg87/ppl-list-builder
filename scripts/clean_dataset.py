import pandas as pd
import csv
from pathlib import Path

def clean_csv(input_path, output_path):
    print(f"Reading from {input_path}...")
    
    # Read the file skipping the first 1420 lines (bad data/old schema)
    # We provide column names manually because there is no header in this section
    col_names = [
        "company_name", 
        "website", 
        "phone", 
        "email", 
        "location", 
        "bus_registered", 
        "certifications", 
        "scraped_at", 
        "source"
    ]
    
    try:
        df = pd.read_csv(
            input_path, 
            skiprows=1420, 
            header=None, 
            names=col_names,
            on_bad_lines='warn' # In case of further inconsistencies
        )
        
        print(f"Loaded {len(df)} rows.")
        
        # Drop unwanted columns
        cols_to_drop = ["website", "email", "scraped_at"]
        print(f"Dropping columns: {cols_to_drop}")
        df = df.drop(columns=cols_to_drop, errors='ignore')
        
        # Optional: Basic data cleaning
        # Ensure bus_registered is boolean
        df['bus_registered'] = df['bus_registered'].astype(bool)
        
        # Deduplicate
        initial_count = len(df)
        df = df.drop_duplicates(subset=['company_name'])
        print(f"Removed {initial_count - len(df)} duplicates.")
        
        # Write to output
        print(f"Writing to {output_path}...")
        df.to_csv(output_path, index=False)
        print("Done.")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    input_file = "output/heat-pump-installers.csv"
    output_file = "output/heat-pump-installers-clean.csv"
    clean_csv(input_file, output_file)
