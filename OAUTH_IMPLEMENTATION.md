# OAuth Backend Integration

Add the following environment variables to your `.env` file:

```
GOOGLE_CLIENT_ID=your_google_client_id_here.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret_here
GITHUB_CLIENT_ID=your_github_client_id_here
GITHUB_CLIENT_SECRET=your_github_client_secret_here
OAUTH_REDIRECT_URI=http://localhost:8000/api/oauth/callback
```

Add this endpoint to main.py after the login endpoint:

```python
@app.get("/api/oauth/callback")
async def oauth_callback(code: str | None = None, error: str | None = None) -> dict[str, Any]:
    """OAuth callback handler for Google and GitHub authentication."""
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    
    if not code:
        raise HTTPException(status_code=400, detail="No authorization code provided")
    
    # TODO: Exchange code for access token
    # TODO: Fetch user info from OAuth provider
    # TODO: Create or update user in database
    # TODO: Return JWT token or session cookie
    
    return {
        "success": True,
        "message": "OAuth callback received",
        "code": code,
    }
```

## Frontend OAuth Handler

The OAuth buttons in register.html and auth.html now include:

```javascript
const GOOGLE_CLIENT_ID = 'your_google_client_id_here.apps.googleusercontent.com';
const GITHUB_CLIENT_ID = 'your_github_client_id_here';
const REDIRECT_URI = `${window.location.origin}/api/oauth/callback`;

function oauthGoogle() {
  const authUrl = new URL('https://accounts.google.com/o/oauth2/v2/auth');
  authUrl.searchParams.append('client_id', GOOGLE_CLIENT_ID);
  authUrl.searchParams.append('redirect_uri', REDIRECT_URI);
  authUrl.searchParams.append('response_type', 'code');
  authUrl.searchParams.append('scope', 'openid email profile');
  window.location.href = authUrl.toString();
}

function oauthGitHub() {
  const authUrl = new URL('https://github.com/login/oauth/authorize');
  authUrl.searchParams.append('client_id', GITHUB_CLIENT_ID);
  authUrl.searchParams.append('redirect_uri', REDIRECT_URI);
  authUrl.searchParams.append('scope', 'user:email');
  window.location.href = authUrl.toString();
}
```

## Testing

1. Update the client IDs in the frontend files
2. Add environment variables to .env
3. Run the server
4. Click the Google or GitHub button
5. Complete the OAuth flow
6. The callback will redirect to `/api/oauth/callback`

## Next Steps for Production

To make this fully functional for production, you need to:

1. Implement token exchange in the backend OAuth endpoint
2. Fetch user info from the OAuth provider
3. Create or link user account in MongoDB
4. Generate JWT or session token
5. Handle redirect to dashboard after successful OAuth login
