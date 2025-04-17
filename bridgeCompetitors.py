import streamlit as st
import json
import requests
from bs4 import BeautifulSoup
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import os
from datetime import datetime, timedelta

# Set page config
st.set_page_config(page_title="Bridge Players Competitions", layout="wide")

# Load players data
@st.cache_data
def load_players():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, "u16Players.json")
    with open(file_path, 'r', encoding='utf-8') as f:
        players = json.load(f)
        # Create a dictionary for player lookup
        return {player['Name']: player for player in players}

# Function to convert Hebrew date to datetime object for sorting
def hebrew_date_to_datetime(hebrew_date):
    try:
        day, month, year = hebrew_date.split('-')
        return datetime.strptime(f"{day}-{month}-{year}", "%d-%m-%Y")
    except:
        return datetime.min  # Return minimal date if parsing fails

# Function to calculate Unix timestamps for BBO links
def get_bbo_time_range():
    today = datetime.now()
    start_date = today - timedelta(days=30)
    start_timestamp = int((start_date - datetime(1970, 1, 1)).total_seconds())
    end_timestamp = int((today - datetime(1970, 1, 1)).total_seconds())
    return start_timestamp, end_timestamp

# Function to scrape player competitions
def get_player_competitions(player):
    nbo_id = player['NBO']
    url = f"https://bridge.co.il/viewer/membermplist.php?id={nbo_id}"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Charset': 'utf-8'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'  # Force UTF-8 encoding
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the specific table with class "mpDetails"
        table = soup.find('table', class_='mpDetails')
        if not table:
            st.warning(f"No table with class 'mpDetails' found for {player['Name']}")
            return []
        
        # Get all rows with class "temp hl" from this table
        rows = table.select('tr.temp.hl')[:10]  # Get top 10 competitions
        
        start_time, end_time = get_bbo_time_range()
        competitions = []
        for row in rows:
            cols = row.find_all('td')
            
            # Extract date (first td)
            date = cols[0].get_text(strip=True) if len(cols) > 0 else ""
            
            # Extract competition name and URL (second td)
            competition_name = ""
            competition_url = ""
            if len(cols) > 1:
                link = cols[1].find('a')
                if link:
                    competition_name = link.get_text(strip=True)
                    competition_url = link.get('href', "")
            
            # Extract points (last td)
            points = cols[-1].get_text(strip=True) if len(cols) > 0 else ""
            
            competitions.append({
                'Date': date,
                'DateSort': hebrew_date_to_datetime(date),  # For sorting
                'Player Name': player['Name'],
                'Competition Name': competition_name,
                'Points': points,
                'Competition URL': competition_url,
                'NBO': f"https://bridge.co.il/viewer/membermplist.php?id={nbo_id}",
                'BBO': f"https://www.bridgebase.com/myhands/hands.php?username={player['BBO']}&start_time={start_time}&end_time={end_time}&from_login=0"                
            })
        
        return competitions
    
    except Exception as e:
        st.error(f"Error fetching data for {player['Name']} (NBO: {nbo_id}): {str(e)}")
        return []

# Main app function
def main():
    st.title("Bridge Players Recent Competitions")
    
    # Load players
    try:
        players_dict = load_players()
        players_list = list(players_dict.values())
        st.success(f"Successfully loaded {len(players_list)} players")
    except Exception as e:
        st.error(f"Failed to load players data: {str(e)}")
        return
    
    # Player selection dropdown
    player_names = ["All Players"] + [player['Name'] for player in players_list]
    selected_player = st.selectbox("Select Player", player_names)
    
    if st.button("Fetch Recent Competitions"):
        st.write("Fetching data... This may take a few moments.")
        
        all_competitions = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            # If "All Players" is selected, fetch all, otherwise just the selected player
            players_to_fetch = players_list if selected_player == "All Players" else [players_dict[selected_player]]
            results = list(executor.map(get_player_competitions, players_to_fetch))
            
            for result in results:
                if result:
                    all_competitions.extend(result)
        
        if all_competitions:
            df = pd.DataFrame(all_competitions)
            
            # Sort by date descending
            df = df.sort_values('DateSort', ascending=False)
            
            # Select and order columns for display
            df = df[['Date', 'Player Name', 'Competition Name', 'Points', 'Competition URL', 'NBO', 'BBO']]
            
            st.subheader(f"Recent Competitions for {selected_player}")
            st.dataframe(
                df,
                column_config={
                    "NBO": st.column_config.LinkColumn("NBO Profile"),
                    "BBO": st.column_config.LinkColumn("BBO Hands"),
                    "Competition URL": st.column_config.LinkColumn("Competition Link"),
                },
                hide_index=True,
                use_container_width=True
            )
            
            # Prepare CSV with UTF-8 encoding
            csv = df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="Download data as CSV",
                data=csv,
                file_name='bridge_players_competitions.csv',
                mime='text/csv',
            )
        else:
            st.warning("No competition data found.")

if __name__ == "__main__":
    main()
