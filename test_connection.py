"""
QuantConnect API Connection Test
This script tests the connection to QuantConnect's API using direct HTTP requests.
"""

import requests
import json
import time
import hashlib

def test_connection():
    """
    Test connection to QuantConnect API.
    Replace USER_ID and API_TOKEN with your actual credentials from:
    https://www.quantconnect.com/account
    """
    
    # Configuration - Using credentials from config_template
    USER_ID = "446417"  # Your QuantConnect user ID
    API_TOKEN = "e94d4e1022e70b6d1940194f2ae2e1540a2edd7e84454bb6900fccb1de66d0d0"  # Your QuantConnect API token
    
    # API Base URL
    BASE_URL = "https://www.quantconnect.com/api/v2"
    
    try:
        # Test connection by getting account information
        print("Testing QuantConnect API connection...")
        
        # Check if credentials are still placeholder values
        if USER_ID == "YOUR_USER_ID" or API_TOKEN == "YOUR_API_TOKEN":
            print("⚠ Warning: Using placeholder credentials")
            print("Please update USER_ID and API_TOKEN in test_connection.py")
            print("Get your credentials from: https://www.quantconnect.com/account")
            return False
        
        # Authenticate and get list of projects
        # QuantConnect API requires timestamp and hash-based authentication
        timestamp = str(int(time.time()))
        
        # Create authentication hash (API_TOKEN:timestamp)
        auth_string = f"{API_TOKEN}:{timestamp}"
        auth_hash = hashlib.sha256(auth_string.encode()).hexdigest()
        
        headers = {
            'Timestamp': timestamp
        }
        
        try:
            response = requests.get(
                f"{BASE_URL}/projects/read",
                auth=(USER_ID, auth_hash),
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('success'):
                    print("✓ Successfully connected to QuantConnect!")
                    
                    projects = data.get('projects', [])
                    print(f"✓ Found {len(projects)} project(s) in your account")
                    
                    # Display project names
                    if projects:
                        print("\nYour projects:")
                        for project in projects[:5]:  # Show first 5
                            print(f"  - {project.get('name', 'Unnamed')} (ID: {project.get('projectId')})")
                    else:
                        print("  (No projects found - create one at https://www.quantconnect.com)")
                    
                    return True
                else:
                    print(f"✗ API returned error: {data.get('errors', 'Unknown error')}")
                    return False
            elif response.status_code == 401:
                print("✗ Authentication failed - Invalid USER_ID or API_TOKEN")
                print("Please verify your credentials at https://www.quantconnect.com/account")
                return False
            else:
                print(f"✗ API request failed with status code: {response.status_code}")
                print(f"Response: {response.text[:200]}")
                return False
                
        except requests.exceptions.Timeout:
            print("✗ Connection timeout - please check your internet connection")
            return False
        except requests.exceptions.ConnectionError:
            print("✗ Connection error - please check your internet connection")
            return False
            
    except Exception as e:
        print(f"✗ Error connecting to QuantConnect: {str(e)}")
        print("\nTroubleshooting:")
        print("1. Verify your credentials at https://www.quantconnect.com/account")
        print("2. Check your internet connection")
        print("3. Make sure you have 'requests' installed: pip install requests")
        return False


def test_basic_algorithm():
    """
    Test a basic QuantConnect algorithm structure (for local testing).
    This demonstrates the algorithm structure without running it.
    """
    from datetime import datetime
    
    print("\n" + "="*60)
    print("Testing Basic Algorithm Structure...")
    print("="*60)
    
    class TestAlgorithm:
        """Basic algorithm structure for testing"""
        
        def __init__(self):
            self.start_date = datetime(2020, 1, 1)
            self.end_date = datetime(2021, 1, 1)
            self.cash = 100000
            
        def Initialize(self):
            """Initialize the algorithm"""
            print(f"✓ Algorithm initialized with ${self.cash:,.2f}")
            print(f"  Start Date: {self.start_date.strftime('%Y-%m-%d')}")
            print(f"  End Date: {self.end_date.strftime('%Y-%m-%d')}")
            
        def OnData(self, data):
            """Handle incoming data"""
            pass
    
    # Create and initialize test algorithm
    algo = TestAlgorithm()
    algo.Initialize()
    print("✓ Basic algorithm structure is valid")


if __name__ == "__main__":
    print("="*60)
    print("QuantConnect Connection Test")
    print("="*60)
    
    # Test API connection
    test_connection()
    
    # Test algorithm structure
    test_basic_algorithm()
    
    print("\n" + "="*60)
    print("Test completed!")
    print("="*60)
