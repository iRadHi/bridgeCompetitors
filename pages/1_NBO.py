import streamlit as st
import json
import requests
from bs4 import BeautifulSoup
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import os
from datetime import datetime, timedelta

# Load players data with improved path handling
@st.cache_data
def load_players():
    """Load player data from JSON file with proper path resolution"""
    try:
        # Handle both standalone execution and multi-page structure
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        json_path = os.path.join(base_dir, "u16Players.json")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            players = json.load(f)
            return {player['Name']: player for player in players}
    except Exception as e:
        st.error(f"Failed to load players data: {str(e)}")
        return {}

# Date conversion with better error handling
def hebrew_date_to_datetime(hebrew_date):
    """Convert Hebrew date string to datetime object"""
    try:
        day, month, year = hebrew_date.split('-')
        return datetime.strptime(f"{day}-{month}-{year}", "%d-%m-%Y")
    except (ValueError, AttributeError):
        return datetime.min  # Return minimal date for sorting

# Competition scraping function with enhanced error handling
def get_player_competitions(player):
    """Scrape competition data for a single player"""
    nbo_id = player.get('NBO', '')
    if not nbo_id:
        st.warning(f"No NBO ID found for {player.get('Name', 'Unknown')}")
        return []

    url = f"https://bridge.co.il/viewer/membermplist.php?id={nbo_id}"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Charset': 'utf-8'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', class_='mpDetails')
        
        if not table:
            st.warning(f"No competition table found for {player['Name']}")
            return []
        
        competitions = []
        for row in table.select('tr.temp.hl')[:3]:  # Top 3 competitions
            cols = row.find_all('td')
            if len(cols) < 2:  # Skip incomplete rows
                continue
                
            date = cols[0].get_text(strip=True)
            link = cols[1].find('a')
            
            competitions.append({
                'Date': date,
                'DateSort': hebrew_date_to_datetime(date),
                'Player Name': player['Name'],
                'Competition Name': link.get_text(strip=True) if link else "Unknown",
                'Points': cols[-1].get_text(strip=True) if cols else "",
                'Competition URL': link.get('href', "") if link else "",
                'NBO Profile': f"https://bridge.co.il/viewer/membermplist.php?id={nbo_id}"
            })
        
        return competitions
    
    except requests.exceptions.RequestException as e:
        st.error(f"Network error fetching data for {player['Name']}: {str(e)}")
    except Exception as e:
        st.error(f"Unexpected error processing {player['Name']}: {str(e)}")
    
    return []

# Main page function
def main():
    st.title("🇮🇱 NBO Competition Results")
    st.markdown("View recent competition results from the Israeli Bridge Federation")
    
    # Load and cache players data
    players_dict = load_players()
    if not players_dict:
        return
    
    players_list = list(players_dict.values())
    
    # Player selection with session state persistence
    if 'selected_player' not in st.session_state:
        st.session_state.selected_player = "All Players"
        
    player_names = ["All Players"] + [player['Name'] for player in players_list]
    selected_player = st.selectbox(
        "Select Player", 
        player_names,
        key='nbo_player_select'
    )
    
    # Fetch button with loading state
    if st.button("Fetch Competitions", key='nbo_fetch_button'):
        with st.spinner("Fetching competition data..."):
            all_competitions = []
            
            with ThreadPoolExecutor(max_workers=5) as executor:
                players_to_fetch = (
                    players_list 
                    if selected_player == "All Players" 
                    else [players_dict[selected_player]]
                )
                results = list(executor.map(get_player_competitions, players_to_fetch))
                
                for result in results:
                    if result:
                        all_competitions.extend(result)
            
            if all_competitions:
                # Process and display data
                df = pd.DataFrame(all_competitions)
                df = df.sort_values('DateSort', ascending=False)
                df = df.drop(columns=['DateSort'])  # Remove sorting helper column
                
                # Display dataframe with customized columns
                st.dataframe(
                    df,
                    column_config={
                        "NBO Profile": st.column_config.LinkColumn("NBO Profile"),
                        "Competition URL": st.column_config.LinkColumn(
                            "Competition Link",
                            help="Link to competition details"
                        ),
                    },
                    hide_index=True,
                    use_container_width=True
                )
                
                # Download option
                csv = df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="Download as CSV",
                    data=csv,
                    file_name='nbo_competitions.csv',
                    mime='text/csv',
                    help="Download all displayed data as CSV file"
                )
            else:
                st.warning("No competition data found for the selected player(s)")

if __name__ == "__main__":
    main()