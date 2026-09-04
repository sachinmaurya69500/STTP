# OAuth Setup Guide for LectureSense

## Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google+ API
4. Create OAuth 2.0 Client ID (Web application)
   - Authorized redirect URIs: `http://localhost:8000/api/oauth/callback`
   - Also add: `http://127.0.0.1:8000/api/oauth/callback`
5. Copy the Client ID and Client Secret

## GitHub OAuth Setup

1. Go to [GitHub Settings > Developer settings > OAuth Apps](https://github.com/settings/developers)
2. Click "New OAuth App"
3. Fill in the form:
   - Application name: LectureSense
   - Homepage URL: `http://localhost:8000`
   - Authorization callback URL: `http://localhost:8000/api/oauth/callback`
4. Copy the Client ID and Client Secret

## Environment Variables

Add these to your `.env` file:

```
# OAuth settings
GOOGLE_CLIENT_ID=your_google_client_id_here.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret_here
GITHUB_CLIENT_ID=your_github_client_id_here
GITHUB_CLIENT_SECRET=your_github_client_secret_here
OAUTH_REDIRECT_URI=http://localhost:8000/api/oauth/callback
```

## Frontend Configuration

Update the client IDs in `auth.html` and `register.html`:

```javascript
const GOOGLE_CLIENT_ID = 'your_google_client_id_here.apps.googleusercontent.com';
const GITHUB_CLIENT_ID = 'your_github_client_id_here';
```

## Test the Flow

1. Run the server: `python -m uvicorn main:app --host 0.0.0.0 --port 8000`
2. Go to `http://localhost:8000/register.html` or `http://localhost:8000/auth.html`
3. Click "Google" or "GitHub" button
4. Complete the OAuth flow
5. You will be redirected to `/api/oauth/callback` with an authorization code
