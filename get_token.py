import json
import urllib.parse
import urllib.request
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler

REDIRECT_PORT = 8080
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"
SCOPES = "https://www.googleapis.com/auth/drive"

auth_code = None

class OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>Authentication Successful!</h1><p>You can close this tab and return to the terminal.</p>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Failed to get authorization code.")
            
    def log_message(self, format, *args):
        return  # Suppress server logs

def get_refresh_token():
    print("=" * 60)
    print(" Google Drive OAuth 2.0 Refresh Token Generator ")
    print("=" * 60)
    
    with open("client_secret.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        client_info = data.get("installed") or data.get("web")
        client_id = client_info["client_id"]
        client_secret = client_info["client_secret"]
    
    auth_params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent"
    }
    
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(auth_params)}"
    
    print("\nOpening your browser for authentication...")
    print(f"URL: {auth_url}\n")
    webbrowser.open(auth_url)
    
    server = HTTPServer(("localhost", REDIRECT_PORT), OAuthHandler)
    print("Waiting for authentication in browser...")
    while auth_code is None:
        server.handle_request()
    server.server_close()
    
    # Exchange auth code for refresh token
    token_url = "https://oauth2.googleapis.com/token"
    token_data = urllib.parse.urlencode({
        "code": auth_code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }).encode("utf-8")
    
    req = urllib.request.Request(token_url, data=token_data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            refresh_token = res_data.get("refresh_token")
            
            if refresh_token:
                output = f"""
============================================================
🎉 SUCCESS! HERE ARE YOUR NEW VARIABLES FOR RAILWAY:
============================================================
GDRIVE_CLIENT_ID:
{client_id}

GDRIVE_CLIENT_SECRET:
{client_secret}

GDRIVE_REFRESH_TOKEN:
{refresh_token}
============================================================
"""
                print(output)
                with open("tokens.txt", "w", encoding="utf-8") as out_f:
                    out_f.write(output)
                print("Saved to tokens.txt successfully!")
            else:
                print("\nError: Did not receive refresh_token. Response:")
                print(res_data)
    except urllib.error.HTTPError as e:
        print(f"\nFailed to get token: {e.read().decode('utf-8')}")

if __name__ == "__main__":
    get_refresh_token()
