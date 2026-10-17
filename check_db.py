import os
import sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv("src/backend/.env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key)
response = supabase.table("requests").select("request_id,status,error_message").execute()
print(response.data)
