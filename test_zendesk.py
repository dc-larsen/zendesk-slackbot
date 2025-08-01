#!/usr/bin/env python3
"""
Quick test script to diagnose Zendesk API connection issues
"""

import os
import sys
from config import ZENDESK_BASE_URL, ZENDESK_EMAIL, ZENDESK_API_TOKEN

def test_zendesk_config():
    """Test if Zendesk configuration is properly set up"""
    print("🔍 Testing Zendesk Configuration...")
    print(f"ZENDESK_BASE_URL: {ZENDESK_BASE_URL}")
    print(f"ZENDESK_EMAIL: {ZENDESK_EMAIL}")
    print(f"ZENDESK_API_TOKEN: {'Set' if ZENDESK_API_TOKEN else 'NOT SET'}")
    
    if not ZENDESK_BASE_URL:
        print("❌ ZENDESK_BASE_URL is not set")
        return False
    
    if not ZENDESK_EMAIL:
        print("❌ ZENDESK_EMAIL is not set")
        return False
        
    if not ZENDESK_API_TOKEN:
        print("❌ ZENDESK_API_TOKEN is not set")
        return False
    
    print("✅ All Zendesk configuration variables are set")
    return True

def test_zendesk_connection():
    """Test Zendesk API connection"""
    try:
        from zendesk_client import ZendeskClient
        
        print("\n🔍 Testing Zendesk API Connection...")
        client = ZendeskClient()
        
        # The connection test is already called in __init__
        print("✅ Zendesk client initialized successfully")
        return True
        
    except Exception as e:
        print(f"❌ Failed to initialize Zendesk client: {e}")
        return False

def main():
    print("🚀 Zendesk API Connection Test\n")
    
    # Test configuration
    config_ok = test_zendesk_config()
    if not config_ok:
        print("\n❌ Configuration issues found. Please check your environment variables.")
        sys.exit(1)
    
    # Test connection
    connection_ok = test_zendesk_connection()
    if not connection_ok:
        print("\n❌ Connection test failed.")
        sys.exit(1)
    
    print("\n🎉 All Zendesk tests passed!")

if __name__ == "__main__":
    main()