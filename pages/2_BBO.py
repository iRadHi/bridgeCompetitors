import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import json
from datetime import datetime, timedelta
import logging
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Free public proxies list
FREE_PROXIES = [
    "51.79.52.80:3128", 
    "212.107.28.120:80",
    "104.148.36.10:80",
    "185.162.230.252:80",
    "188.166.56.246:80",
    "51.159.115.233:3128",
    "169.57.1.85:8123",
    "20.210.113.32:8123",
    "47.88.3.19:8080",
    "51.75.122.80:80",
    "103.155.217.52:41472",
    "181.129.70.82:46752",
    "78.47.223.55:5566",
    "176.192.70.58:8008",
    "122.9.101.6:8888"
]

# Load players data
@st.cache_data
def load_players():
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        json_path = os.path.join(base_dir, "u16Players.json")
        with open(json_path, 'r', encoding='utf-8') as f:
            players = json.load(f)
            return {player['Name']: player for player in players}
    except Exception as e:
        st.error(f"Failed to load players data: {str(e)}")
        return {}

def get_unix_timestamp(days_back):
    return int((datetime.now() - timedelta(days=days_back)).timestamp())

def get_bbo_time_range(timeframe):
    timeframes = {
        "Last Day": 1,
        "Last Week": 7,
        "Last 2 Weeks": 14,
        "Last Month": 30
    }
    days = timeframes.get(timeframe, 30)
    return get_unix_timestamp(days), get_unix_timestamp(0)

def parse_cookie_text(cookie_text):
    """Parse cookies in various formats"""
    try:
        # Try JSON format first
        cookies = json.loads(cookie_text)
        if isinstance(cookies, list):
            return {c['name']: c['value'] for c in cookies}
        return cookies
    except:
        # Try simple name=value format
        cookies = {}
        for line in cookie_text.split('\n'):
            if '=' in line:
                parts = line.strip().split('=', 1)
                cookies[parts[0]] = parts[1]
        return cookies

def manual_login():
    """Fallback for manual cookie injection"""
    st.warning("""
    If automated login fails:
    1. Login manually in Chrome/Firefox
    2. Install 'EditThisCookie' extension
    3. Export your BBO cookies as JSON
    4. Paste them below
    """)
    
    cookies = st.text_area("Paste cookies (JSON format or name=value format):", height=150)
    if st.button("Use Manual Cookies"):
        try:
            session = requests.Session()
            cookies_dict = parse_cookie_text(cookies)
            
            requests.utils.add_dict_to_cookiejar(session.cookies, cookies_dict)
            
            # Verify session
            test_url = "https://www.bridgebase.com/myhands/index.php"
            response = session.get(test_url, timeout=10)
            
            if 'logout.php' in response.text:
                st.success("✅ Manual cookies verified!")
                return session
            else:
                st.error("❌ Cookies don't provide valid session")
                with st.expander("Response Details", expanded=False):
                    st.write("Status Code:", response.status_code)
                    st.write("Response Length:", len(response.text))
                    st.code(response.text[:500])
        except Exception as e:
            st.error(f"Invalid cookies: {str(e)}")
    return None

def get_local_timezone_offset():
    """Get local timezone offset in minutes"""
    utc_offset = datetime.now().astimezone().utcoffset()
    return int(utc_offset.total_seconds() / 60)

def handle_timezone_redirect(session, proxy=None):
    """Handle the timezone JavaScript redirect by manually sending the timezone offset"""
    try:
        # Calculate local timezone offset (JS would normally do this)
        offset = get_local_timezone_offset()
        logger.info(f"Using timezone offset: {offset} minutes")
        
        # Submit the timezone form data
        tz_url = "https://www.bridgebase.com/myhands/index.php?&from_login=1"
        tz_data = {"offset": str(offset)}
        
        session.headers.update({
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'https://www.bridgebase.com/myhands/index.php'
        })
        
        response = session.post(
            tz_url,
            data=tz_data,
            allow_redirects=True,
            timeout=15,
            proxies=proxy
        )
        
        # Verify we reached the main page
        if 'logout.php' in response.text:
            logger.info("Successfully handled timezone redirect")
            return True
        else:
            # Alternative: try direct timezone URL
            alt_url = f"https://www.bridgebase.com/myhands/index.php?offset={offset}"
            alt_response = session.get(alt_url, proxies=proxy)
            
            if 'logout.php' in alt_response.text:
                logger.info("Successfully handled timezone redirect via alternative URL")
                return True
            
            logger.warning("Failed to handle timezone redirect")
            return False
    
    except Exception as e:
        logger.error(f"Error handling timezone redirect: {str(e)}")
        return False

def login_to_bbo(username, password, proxy=None):
    """Enhanced BBO login with proper form submission and timezone handling"""
    try:
        session = requests.Session()
        
        # Set realistic browser headers
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1'
        })

        # Step 1: Get initial cookies from home page
        st.info("🔄 Initializing session...")
        home_url = "https://www.bridgebase.com/myhands/"
        session.get(home_url, timeout=10, proxies=proxy)
        time.sleep(random.uniform(1.5, 3.0))  # Random delay to mimic human behavior

        # Step 2: Load the login page
        st.info("🔑 Loading login form...")
        login_page_url = "https://www.bridgebase.com/myhands/myhands_login.php"
        session.headers.update({'Referer': home_url})
        
        login_page_response = session.get(login_page_url, timeout=10, proxies=proxy)
        
        # Extract CSRF token or form fields if present
        soup = BeautifulSoup(login_page_response.text, 'html.parser')
        
        # Find hidden fields in the form
        form = soup.find('form', method='post')
        hidden_fields = {}
        
        if form:
            for input_field in form.find_all('input', type='hidden'):
                name = input_field.get('name')
                value = input_field.get('value')
                if name:
                    hidden_fields[name] = value
                    logger.info(f"Found hidden field: {name}={value}")
        
        # Add critical target parameter if not found
        if 't' not in hidden_fields:
            hidden_fields['t'] = '/myhands/index.php?'
            logger.info("Added required target parameter")
            
        if 'count' not in hidden_fields:
            hidden_fields['count'] = '1'
            logger.info("Added required count parameter")
        
        time.sleep(random.uniform(1.0, 2.5))  # Another random delay

        # Step 3: Submit the login form with all required fields
        st.info("📨 Authenticating...")
        login_handler_url = "https://www.bridgebase.com/myhands/myhands_login.php"
        
        # Prepare the login data with all fields
        login_data = {
            'username': username,
            'password': password,
            'submit': 'Login',
            'keep': 'on'  # "Keep me logged in" checkbox
        }
        
        # Add any hidden fields we found
        login_data.update(hidden_fields)
        
        # Debugging
        logger.info(f"Submitting form with fields: {list(login_data.keys())}")
        
        session.headers.update({
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://www.bridgebase.com',
            'Referer': login_page_url
        })
        
        # Wait before submitting (anti-bot measure)
        time.sleep(random.uniform(2.0, 4.0))
        
        login_response = session.post(
            login_handler_url,
            data=login_data,
            allow_redirects=True,
            timeout=15,
            proxies=proxy
        )
        
        # Check if we hit the timezone JavaScript page
        if 'Javascript support is needed for this page' in login_response.text:
            st.info("🕒 Handling timezone redirect...")
            timezone_handled = handle_timezone_redirect(session, proxy)
            if not timezone_handled:
                st.warning("⚠️ Timezone handling unsuccessful, but continuing...")
        
        # Verification - check we reached index.php
        test_url = "https://www.bridgebase.com/myhands/index.php"
        test_response = session.get(test_url, timeout=10, proxies=proxy)
        
        if 'logout.php' in test_response.text:
            st.success("✅ Login successful!")
            return session
            
        # Detailed error analysis
        with st.expander("🔍 Login Failure Analysis", expanded=True):
            st.write("Status Code:", login_response.status_code)
            st.write("Final URL:", login_response.url)
            st.write("Response Length:", len(login_response.text))
            st.write("Form Data Submitted:", login_data)
            
            if 'Javascript support is needed' in login_response.text:
                st.error("JavaScript required - session creation incomplete")
                st.info("Consider using Manual Cookies method instead")
            elif login_response.url.endswith("myhands_login.php"):
                st.error("Login failed - credentials rejected or form not submitted")
            elif "Invalid username or password" in login_response.text:
                st.error("BBO rejected the credentials")
            
            st.text("Response snippet:")
            st.code(login_response.text[:1000])
        
        return None

    except Exception as e:
        st.error(f"🚨 Login error: {str(e)}")
        return None

def scrape_bbo_hands(session, url, proxy=None, silent=False):
    """Enhanced scraping with proxy support and better error handling"""
    try:
        # Refresh session 
        maint_url = "https://www.bridgebase.com/myhands/index.php"
        refresh_resp = session.get(maint_url, timeout=10, proxies=proxy)
        
        if 'login.php' in refresh_resp.url:
            st.error("Session has expired. Please login again.")
            return None, None
            
        time.sleep(random.uniform(0.5, 1.5))

        # Configure request
        headers = {
            'Referer': 'https://www.bridgebase.com/myhands/index.php',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1'
        }
        
        # Execute request
        logger.info(f"Fetching: {url}")
        if not silent:
            st.info(f"Retrieving data from BBO...")
        time.sleep(random.uniform(1.0, 2.5))  # More human-like delay
        
        response = session.get(
            url,
            headers=headers,
            timeout=15,
            allow_redirects=True,
            proxies=proxy
        )

        # Check response
        if 'login.php' in response.url:
            logger.warning("Session expired")
            st.error("Session expired during data retrieval")
            return None, None
        
        if 'Javascript support is needed' in response.text:
            if not silent:
                st.warning("Hit JavaScript requirement - trying to handle timezone...")
            handle_timezone_redirect(session, proxy)
            
            # Try again after timezone handling
            time.sleep(random.uniform(1.0, 2.0))
            response = session.get(url, headers=headers, timeout=15, proxies=proxy)
            
        if "You have no saved hands" in response.text:
            logger.info("No hands found")
            return None, None
            
        # Parse response
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try different table selectors
        table_selectors = [
            'table.body',
            'table#hand_results',
            'table.hands',
            'table.handlist'  # Adding another possible selector
        ]
        
        table = None
        for selector in table_selectors:
            table = soup.select_one(selector)
            if table:
                break
                
        # If still not found, try a more generic approach
        if not table:
            tables = soup.find_all('table')
            for potential_table in tables:
                # Look for tables with certain characteristics of hand records
                if potential_table.find_all('tr') and len(potential_table.find_all('tr')) > 1:
                    headers = potential_table.find_all('th')
                    if headers and any('date' in h.text.lower() for h in headers if h.text):
                        table = potential_table
                        break
        
        if table:
            return soup, table
        else:
            logger.warning("No table found")
            if not silent:
                with st.expander("Raw Response", expanded=False):
                    st.text(response.text[:2000])
            return None, None
            
    except Exception as e:
        logger.error(f"Scraping error: {str(e)}")
        if not silent:
            st.error(f"Error retrieving data: {str(e)}")
        return None, None

def extract_player_statistics(soup):
    """Extract player statistics from the soup"""
    stats = {
        'IMPs_Total': 0,
        'IMPs_Hands': 0,
        'IMPs_Average': 0,
        'MPs_Average': 0,
        'MPs_Hands': 0,
        'Total_Masterpoints': 0
    }
    
    try:
        # Find all rows with 'totals' class or content
        total_rows = soup.find_all('tr', class_=['odd', 'even'])
        for row in total_rows:
            if not row.find_all('th') or not row.find_all('td'):
                continue
                
            th_elements = row.find_all('th')
            if not th_elements:
                continue
                
            label = th_elements[0].get_text().strip()
            
            # Extract IMPs Total
            if "IMPs Total" in label:
                score_cell = row.find('td', class_=['score', 'negscore'])
                if score_cell:
                    stats['IMPs_Total'] = float(score_cell.text.strip())
                numhands_cell = row.find('td', class_='numhands')
                if numhands_cell:
                    stats['IMPs_Hands'] = int(numhands_cell.text.strip())
            
            # Extract IMPs Average
            elif "IMPs Average" in label:
                score_cell = row.find('td', class_=['score', 'negscore'])
                if score_cell:
                    stats['IMPs_Average'] = float(score_cell.text.strip())
            
            # Extract MPs Average
            elif "MPs Average" in label:
                score_cell = row.find('td', class_='score')
                if score_cell:
                    # Remove % sign if present
                    mp_avg = score_cell.text.strip().replace('%', '')
                    stats['MPs_Average'] = float(mp_avg)
                numhands_cell = row.find('td', class_='numhands')
                if numhands_cell:
                    stats['MPs_Hands'] = int(numhands_cell.text.strip())
            
            # Extract Total Masterpoints
            elif "Total Masterpoints" in label:
                score_cell = row.find('td', class_='score')
                if score_cell:
                    stats['Total_Masterpoints'] = float(score_cell.text.strip())
    
    except Exception as e:
        logger.error(f"Error extracting statistics: {str(e)}")
    
    return stats

def main():
    st.set_page_config(
        page_title="BBO Hand Records",
        page_icon="♠️",
        layout="wide"
    )
    st.title("♠️ BBO Hand Records")

    # Create sidebar for login
    with st.sidebar:
        st.header("Login")
        
        # Login Section
        login_method = st.radio(
            "Login Method",
            ["Automatic", "Manual Cookies"],
            horizontal=True,
            index=0
        )

        session = None
        proxy_config = None

        # Proxy section with default free proxies
        if login_method == "Automatic":
            with st.form("auto_login"):
                username = st.text_input("BBO Username")
                password = st.text_input("BBO Password", type="password")
                
                proxy_type = st.radio(
                    "Proxy Type",
                    ["None", "Manual", "Public"],
                    horizontal=True
                )
                
                if proxy_type == "Manual":
                    proxy = st.text_input(
                        "Custom Proxy", 
                        help="Format: http://user:pass@host:port"
                    )
                elif proxy_type == "Public":
                    proxy = st.selectbox(
                        "Select a Free Proxy",
                        options=FREE_PROXIES
                    )
                else:
                    proxy = ""
                
                if st.form_submit_button("Login"):
                    with st.spinner("Authenticating..."):
                        if proxy and proxy.strip():
                            if not proxy.startswith("http"):
                                proxy = f"http://{proxy}"
                            proxy_config = {"http": proxy, "https": proxy}
                        session = login_to_bbo(username, password, proxy_config)
        else:
            session = manual_login()

    # Store session in session state to persist across reruns
    if session:
        st.session_state.session = session
        st.session_state.proxy_config = proxy_config
        
    # Check if we have a session (either new or from session state)
    if hasattr(st.session_state, 'session'):
        session = st.session_state.session
        proxy_config = getattr(st.session_state, 'proxy_config', None)
        
        # Main Functionality - Now with persistent UI
        st.success("✅ Logged in successfully!")
        
        # Always display these UI elements regardless of selection state
        players_dict = load_players()
        if players_dict:
            # Using columns for the selection UI
            col1, col2 = st.columns(2)
            
            with col1:
                # Create player selection dropdown
                player_names = ["All Players"] + sorted([p['Name'] for p in players_dict.values()])
                selected_player = st.selectbox("Select Player", player_names, key="player_dropdown")
            
            with col2:
                # Create timeframe selection dropdown
                timeframe = st.selectbox(
                    "Time Frame",
                    ["Last Month", "Last Week", "Last 2 Weeks", "Last Day"],
                    index=0,
                    key="timeframe_dropdown"
                )

            # Create a specific data container for results - this will remain visible
            results_container = st.container()
                
            if st.button("Fetch Hand Records"):
                if selected_player == "All Players":
                    # Create a list to store all player statistics
                    all_players_stats = []
                    start_time, end_time = get_bbo_time_range(timeframe)
                    
                    with results_container:
                        st.subheader(f"Player Statistics Summary ({timeframe})")
                        progress_bar = st.progress(0)
                        
                        # Use a status message that gets updated rather than creating new messages
                        status_message = st.empty()
                        
                        for idx, (name, player) in enumerate(players_dict.items()):
                            if not player.get('BBO'):
                                continue
                                
                            # Update progress
                            progress = (idx + 1) / len(players_dict)
                            progress_bar.progress(progress)
                            
                            # Update the status message rather than creating a new line
                            status_message.info(f"Fetching data for {player['Name']} ({idx+1}/{len(players_dict)})...")
                            
                            url = (
                                f"https://www.bridgebase.com/myhands/hands.php?"
                                f"username={player['BBO']}&"
                                f"start_time={start_time}&"
                                f"end_time={end_time}&"
                                f"from_login=0"
                            )
                            
                            # Use silent mode to suppress individual info messages
                            soup, table = scrape_bbo_hands(session, url, proxy_config, silent=True)
                            
                            if soup and table:
                                # Extract statistics
                                stats = extract_player_statistics(soup)
                                
                                # Create player statistics entry
                                player_entry = {
                                    'Player Name': player['Name'],
                                    'BBO Username': player['BBO'],
                                    'Total Hands': stats['IMPs_Hands'] + stats['MPs_Hands'],
                                    'IMPs Hands': stats['IMPs_Hands'],
                                    'IMPs Total': stats['IMPs_Total'],
                                    'IMPs Average': stats['IMPs_Average'],
                                    'MPs Hands': stats['MPs_Hands'],
                                    'MPs Average': f"{stats['MPs_Average']}%",
                                    'BBO Link': url
                                }
                                all_players_stats.append(player_entry)
                        
                        # Clear status message once done
                        status_message.empty()
                        
                        # Create DataFrame and sort by total hands
                        if all_players_stats:
                            df = pd.DataFrame(all_players_stats)
                            df = df.sort_values('Total Hands', ascending=False)
                            
                            # Convert BBO Link to clickable hyperlinks
                            df['BBO Link'] = df['BBO Link'].apply(lambda x: f'<a href="{x}" target="_blank">Link</a>')
                            
                            # Apply custom CSS to mimic Streamlit table styling
                            st.markdown("""
                            <style>
                            .stTable table {
                                width: 100%;
                                border-collapse: collapse;
                                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                            }
                            .stTable th, .stTable td {
                                padding: 8px 12px;
                                text-align: left;
                                border-bottom: 1px solid #e6e6e6;
                            }
                            .stTable th {
                                background-color: #f5f5f5;
                                font-weight: 600;
                            }
                            .stTable tr:hover {
                                background-color: #f0f2f6;
                            }
                            .stTable a {
                                color: #0068c9;
                                text-decoration: none;
                            }
                            .stTable a:hover {
                                text-decoration: underline;
                            }
                            </style>
                            <div class="stTable">
                            """, unsafe_allow_html=True)
                            
                            # Display final dataframe with clickable links
                            st.markdown(df.to_html(escape=False, index=False), unsafe_allow_html=True)
                            st.markdown("</div>", unsafe_allow_html=True)
                            
                            # Download options
                            csv = df.drop(columns=['BBO Link']).to_csv(index=False, encoding='utf-8-sig')
                            st.download_button(
                                "Download as CSV",
                                data=csv,
                                file_name=f"bbo_stats_all_players.csv",
                                mime="text/csv"
                            )
                        else:
                            st.warning("No data found for any players")
                else:
                    # Single player mode
                    player = players_dict[selected_player]
                    
                    if not player.get('BBO'):
                        st.warning(f"No BBO username found for {player['Name']}")
                    else:
                        start_time, end_time = get_bbo_time_range(timeframe)
                        url = (
                            f"https://www.bridgebase.com/myhands/hands.php?"
                            f"username={player['BBO']}&"
                            f"start_time={start_time}&"
                            f"end_time={end_time}&"
                            f"from_login=0"
                        )

                        with results_container:
                            st.subheader(f"Hand Records for {player['Name']} ({timeframe})")
                            
                            with st.spinner(f"Fetching data for {player['Name']}..."):
                                soup, table = scrape_bbo_hands(session, url, proxy_config)
                                if soup and table:
                                    try:
                                        try:
                                            df = pd.read_html(str(table), flavor='lxml')[0]
                                        except ImportError:
                                            df = pd.read_html(str(table), flavor='html5lib')[0]
                                        
                                        # Process the DataFrame
                                        # 1. Remove index column if it exists
                                        if df.columns[0] is not None and isinstance(df.columns[0], str) and df.columns[0].startswith('Unnamed'):
                                            df = df.iloc[:, 1:]
                                            
                                        # 2. Remove 'Movie' and 'Traveller' columns if they exist
                                        #columns_to_drop = [col for col in df.columns if col in ['Movie', 'Traveller']]
                                        #if columns_to_drop:
                                        #    df = df.drop(columns=columns_to_drop)
                                        # 2. Remove the last two columns (Movie and Traveller)
                                        df = df.iloc[:, :-2]
                                        
                                        # 3. Ensure the first column is "Nº." and remove auto-index
                                        if "Nº." in df.columns:
                                            first_col = "Nº."
                                            cols = [first_col] + [col for col in df.columns if col != first_col]
                                            df = df[cols]
                                        
                                        # Display without index
                                        st.dataframe(df, use_container_width=True, hide_index=True)
                                        st.success(f"Found {len(df)} records")
                                        
                                        # Download options
                                        csv = df.to_csv(index=False, encoding='utf-8-sig')
                                        st.download_button(
                                            "Download as CSV",
                                            data=csv,
                                            file_name=f"bbo_hands_{player['Name']}.csv",
                                            mime="text/csv"
                                        )
                                        
                                        # Display player statistics
                                        stats = extract_player_statistics(soup)
                                        if any(stats.values()):
                                            st.subheader("Player Statistics")
                                            st.write(f"Total Hands: {stats['IMPs_Hands'] + stats['MPs_Hands']}")
                                            st.write(f"IMPs Hands: {stats['IMPs_Hands']}")
                                            st.write(f"IMPs Total: {stats['IMPs_Total']}")
                                            st.write(f"IMPs Average: {stats['IMPs_Average']}")
                                            st.write(f"MPs Hands: {stats['MPs_Hands']}")
                                            st.write(f"MPs Average: {stats['MPs_Average']}%")
                                            st.write(f"Total Masterpoints: {stats['Total_Masterpoints']}")
                                        
                                    except Exception as e:
                                        st.error(f"Error processing table: {str(e)}")
                                        st.exception(e)  # Show full traceback for debugging
                                else:
                                    st.warning("No hand records found")
                                    st.info("This could mean either the player has no records in this time period, or there was an issue accessing the data.")

if __name__ == "__main__":
    main()
