import requests
import csv
import time
import os
import re
from datetime import datetime, timezone # <-- This line was missing

# --- CONFIGURATION ---
# Replace with your actual Dell TechDirect API credentials
CLIENT_ID = "<CLIENT-ID>"
CLIENT_SECRET = "<CLIENT-SECRET>"

SERVICE_TAGS = [
"<SC-TAG1>",
"<SC-TAG2>"
]

OUTPUT_CSV_FILE = "dell_summary_inventory.csv"
FAILED_LOG_FILE = "failed_tags.log"

# API endpoints from documentation
TOKEN_URL = "https://apigtwb2c.us.dell.com/auth/oauth/v2/token"
ASSET_COMPONENTS_URL = "https://apigtwb2c.us.dell.com/PROD/sbil/eapi/v5/asset-components"
ASSET_ENTITLEMENTS_URL = "https://apigtwb2c.us.dell.com/PROD/sbil/eapi/v5/asset-entitlements"

# --- HELPER FUNCTIONS ---

def get_access_token():
    print("Getting new access token...")
    payload = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'client_credentials'}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    try:
        response = requests.post(TOKEN_URL, headers=headers, data=payload)
        response.raise_for_status()
        token = response.json().get('access_token')
        if not token: print("Error: Could not retrieve access token.")
        else: print("Access token received.")
        return token
    except requests.exceptions.RequestException as e:
        print(f"HTTP Request failed during auth: {e}")
        return None

def get_api_data(token, tag, log_file, url):
    """Generic function to get data from a Dell API endpoint."""
    params = {'servicetags': tag}
    if 'asset-components' in url:
        params = {'servicetag': tag}
    
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        print(f"Warning: HTTP error for tag '{tag}' at {url}. Reason: {e}")
        log_file.write(f"{tag} - {url}\n")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Warning: Network error for tag '{tag}' at {url}. Reason: {e}")
        log_file.write(f"{tag} - {url}\n")
        return None

def format_components(counts_dict):
    """Takes a dictionary of component counts and returns a formatted string."""
    if not counts_dict:
        return "N/A"
    return "; ".join([f"{count} x {desc}" for desc, count in counts_dict.items()])

# --- MAIN LOGIC ---

def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("Error: API credentials not found. Please set environment variables.")
        return

    access_token = get_access_token()
    if not access_token: return

    print(f"\n Processing {len(SERVICE_TAGS)} tags...")
    
    # Define headers for the single-line summary
    headers = ['serviceTag', 'productLineDescription', 'shipDate', 'Active_Warranties', 'All_Components']
    
    with open(OUTPUT_CSV_FILE, mode='w', newline='', encoding='utf-8') as csv_file, \
         open(FAILED_LOG_FILE, mode='w', encoding='utf-8') as log_file:
        
        writer = csv.writer(csv_file)
        writer.writerow(headers)
        
        now_utc = datetime.now(timezone.utc)

        for tag in SERVICE_TAGS:
            print(f"  -> Fetching data for {tag}...")
            asset_hardware = get_api_data(access_token, tag, log_file, ASSET_COMPONENTS_URL)
            asset_warranty_data = get_api_data(access_token, tag, log_file, ASSET_ENTITLEMENTS_URL)
            
            asset_warranty = asset_warranty_data[0] if asset_warranty_data else None

            if not asset_hardware or not asset_warranty:
                print(f"  -> Skipping tag {tag} due to failed API call.")
                continue
            
            # --- Process Warranty Information ---
            active_warranties = []
            for w in asset_warranty.get('entitlements', []):
                try:
                    end_date_str = w.get('endDate')
                    end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                    if end_date > now_utc:
                        desc = w.get('serviceLevelDescription')
                        date_str = end_date.strftime('%Y-%m-%d')
                        active_warranties.append(f"{desc} (Expires: {date_str})")
                except (ValueError, TypeError):
                    continue
            warranties_string = "; ".join(active_warranties) if active_warranties else "N/A"

            # --- Process and Consolidate All Hardware Components ---
            component_counts = {}
            noise_filter = ['info', 'information', 'placeholder', 'no item', 'no operating system']
            for comp in asset_hardware.get('components', []):
                desc = comp.get('partDescription')
                qty = comp.get('partQuantity', 1)
                
                # Filter out useless informational components and descriptions
                if not desc or any(noise in desc.lower() for noise in noise_filter):
                    continue
                
                component_counts[desc] = component_counts.get(desc, 0) + qty

            components_string = format_components(component_counts)

            # --- Write the single, consolidated row to the CSV ---
            row = [
                asset_hardware.get('serviceTag'),
                asset_hardware.get('productLineDescription'),
                asset_hardware.get('shipDate'),
                warranties_string,
                components_string
            ]
            writer.writerow(row)
            
            time.sleep(0.3)

    print(f"\nSuccess! Summary inventory report saved to: {OUTPUT_CSV_FILE}")

if __name__ == "__main__":
    main()
