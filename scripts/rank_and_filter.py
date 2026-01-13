import pandas as pd
import argparse
import sys
from pathlib import Path

def rank_and_filter():
    parser = argparse.ArgumentParser(description="Rank and filter companies for enrichment strategy")
    parser.add_argument("--input", required=True, help="Input CSV file")
    parser.add_argument("--output", required=True, help="Output CSV file")
    parser.add_argument("--mode", choices=["sort_bus", "filter_fb_positive"], required=True, 
                        help="Mode: 'sort_bus' (prioritize BUS registered) or 'filter_fb_positive' (keep only FB ads running)")
    parser.add_argument("--limit", type=int, help="Limit output to top N rows")
    
    args = parser.parse_args()
    
    try:
        print(f"Reading {args.input}...")
        df = pd.read_csv(args.input)
        
        if args.mode == "sort_bus":
            print("Sorting by BUS registered status (True first)...")
            # Ensure boolean consistency
            if 'bus_registered' in df.columns:
                df['bus_registered'] = df['bus_registered'].astype(str).map({'True': True, 'False': False, 'true': True, 'false': False})
                df = df.sort_values(by='bus_registered', ascending=False)
            else:
                print("Warning: 'bus_registered' column not found!")
                
        elif args.mode == "filter_fb_positive":
            print("Filtering for companies running Facebook Ads...")
            if 'facebook_ads_running' in df.columns:
                df = df[df['facebook_ads_running'] == True]
            else:
                print("Error: 'facebook_ads_running' column not found. Did you run FB enrichment first?")
                return

        if args.limit:
            print(f"Limiting to top {args.limit} rows...")
            df = df.head(args.limit)
            
        print(f"Writing {len(df)} rows to {args.output}...")
        df.to_csv(args.output, index=False)
        print("Done.")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    rank_and_filter()
