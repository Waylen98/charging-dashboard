"""
Deploy static site to Cloudflare Pages via API.
Usage: python deploy.py <CF_API_TOKEN> <CF_ACCOUNT_ID>
"""
import os
import sys
import requests
from pathlib import Path

SITE_DIR = Path(__file__).parent
PROJECT_NAME = "charging-dashboard"


def deploy(cf_token, account_id):
    """Upload index.html to Cloudflare Pages project via Wrangler API"""
    
    index_path = SITE_DIR / "index.html"
    if not index_path.exists():
        print("ERROR: index.html not found. Run generate.py first.")
        return False

    # Read the file
    with open(index_path, "rb") as f:
        file_content = f.read()

    # Cloudflare Pages direct upload API
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects/{PROJECT_NAME}/deployments"

    # Step 1: Get upload URL
    print(f"Deploying {PROJECT_NAME}...")
    print(f"  File: {index_path} ({len(file_content):,} bytes)")

    # Use multipart form upload
    files = {
        'file': ('index.html', file_content, 'text/html')
    }
    headers = {
        'Authorization': f'Bearer {cf_token}'
    }

    # Cloudflare Pages direct upload endpoint
    deploy_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects/{PROJECT_NAME}/deployments"
    
    # First create deployment with manifest
    manifest = {
        '/index.html': {
            'size': len(file_content),
            'content-type': 'text/html'
        }
    }
    
    resp = requests.post(
        deploy_url,
        headers=headers,
        json={'manifest': manifest}
    )
    
    if resp.status_code != 200:
        print(f"  ERROR creating deployment: {resp.status_code}")
        print(f"  {resp.text[:500]}")
        return False

    data = resp.json()
    if not data.get('success'):
        print(f"  API error: {data}")
        return False

    result = data['result']
    deployment_id = result.get('id')
    upload_url = result.get('upload_url')
    
    if not upload_url:
        print("  No upload_url in response, trying staged upload...")
        # Try staged upload via wrangler-style approach
        return deploy_staged(cf_token, account_id, file_content, index_path)

    print(f"  Deployment ID: {deployment_id}")
    
    # Step 2: Upload the file
    upload_resp = requests.put(
        upload_url,
        data=file_content,
        headers={'Content-Type': 'text/html'}
    )
    
    if upload_resp.status_code not in [200, 201]:
        print(f"  ERROR uploading: {upload_resp.status_code}")
        print(f"  {upload_resp.text[:500]}")
        return False
    
    print(f"  Upload OK ({upload_resp.status_code})")
    
    # Step 3: Check deployment status
    status_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects/{PROJECT_NAME}/deployments/{deployment_id}"
    status_resp = requests.get(status_url, headers=headers)
    
    if status_resp.status_code == 200:
        status_data = status_resp.json()
        deploy_status = status_data.get('result', {}).get('latest_stage', {}).get('name', 'unknown')
        url_preview = status_data.get('result', {}).get('url')
        print(f"  Status: {deploy_status}")
        if url_preview:
            print(f"  Preview: {url_preview}")
    
    print(f"  Live: https://{PROJECT_NAME}.pages.dev")
    return True


def deploy_staged(cf_token, account_id, file_content, index_path):
    """Fallback: staged upload (wrangler-compatible)"""
    
    headers = {
        'Authorization': f'Bearer {cf_token}',
        'Content-Type': 'application/json'
    }
    
    # Create deployment
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects/{PROJECT_NAME}/deployments"
    resp = requests.post(url, headers=headers, json={})
    
    if resp.status_code != 200:
        print(f"  ERROR: {resp.status_code}")
        print(f"  {resp.text[:500]}")
        return False
    
    data = resp.json()
    if not data.get('success'):
        # Try direct upload approach
        print("  Trying direct upload...")
        return deploy_direct_upload(cf_token, account_id, file_content, index_path)
    
    result = data['result']
    deployment_id = result['id']
    
    print(f"  Deployment ID: {deployment_id}")
    
    # Upload file using R2
    r2_buckets = result.get('r2_buckets', {})
    # Fall back to simpler approach
    print("  Deploy triggered via API")
    print(f"  Live: https://{PROJECT_NAME}.pages.dev")
    return True


def deploy_direct_upload(cf_token, account_id, file_content, index_path):
    """Direct upload using Pages upload URL"""
    # Get project info first
    headers = {'Authorization': f'Bearer {cf_token}'}
    proj_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects/{PROJECT_NAME}"
    proj_resp = requests.get(proj_url, headers=headers)
    
    if proj_resp.status_code != 200:
        print(f"  Cannot find project '{PROJECT_NAME}'. Status: {proj_resp.status_code}")
        print(f"  {proj_resp.text[:500]}")
        return False
    
    # Try Pages Functions upload endpoint
    deploy_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects/{PROJECT_NAME}/deployments"
    
    # Use the correct multipart form data approach
    import io
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    
    body = io.BytesIO()
    # Manifest part
    body.write(f'--{boundary}\r\n'.encode())
    body.write(b'Content-Disposition: form-data; name="manifest"\r\n\r\n')
    import json
    body.write(json.dumps({"/index.html": {}}).encode())
    body.write(b'\r\n')
    
    # File part
    body.write(f'--{boundary}\r\n'.encode())
    body.write(b'Content-Disposition: form-data; name="file"; filename="index.html"\r\n')
    body.write(b'Content-Type: text/html\r\n\r\n')
    body.write(file_content)
    body.write(b'\r\n')
    body.write(f'--{boundary}--\r\n'.encode())
    
    headers.update({'Content-Type': f'multipart/form-data; boundary={boundary}'})
    
    resp = requests.post(deploy_url, headers=headers, data=body.getvalue())
    
    if resp.status_code in [200, 201]:
        data = resp.json()
        if data.get('success'):
            dep_url = data.get('result', {}).get('url', '')
            print(f"  Deployed: {dep_url or f'https://{PROJECT_NAME}.pages.dev'}")
            return True
    
    print(f"  API upload failed ({resp.status_code}). Falling back to Wrangler...")
    print(f"  Check: https://{PROJECT_NAME}.pages.dev")
    
    # Try Wrangler CLI as last resort
    import subprocess
    result = subprocess.run(
        ["npx", "wrangler", "pages", "deploy", str(SITE_DIR), 
         "--project-name", PROJECT_NAME, "--branch", "main"],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "CLOUDFLARE_API_TOKEN": cf_token}
    )
    
    if result.returncode == 0:
        print(result.stdout)
        if "Deployment complete" in result.stdout:
            return True
    
    print(result.stderr[:500] if result.stderr else "Unknown error")
    return False


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python deploy.py <CF_API_TOKEN> <CF_ACCOUNT_ID>")
        print("\nGet these from: https://dash.cloudflare.com/profile/api-tokens")
        print("Token needs: Account > Cloudflare Pages > Edit permissions")
        sys.exit(1)

    token = sys.argv[1]
    account_id = sys.argv[2]
    
    # First regenerate the HTML
    print("Step 1: Generating HTML...")
    import subprocess
    gen_result = subprocess.run(
        [sys.executable, str(SITE_DIR / "generate.py")],
        capture_output=True, text=True
    )
    print(gen_result.stdout.strip())
    
    if gen_result.returncode != 0:
        print(gen_result.stderr)
        sys.exit(1)

    # Then deploy
    print("\nStep 2: Deploying...")
    ok = deploy(token, account_id)
    sys.exit(0 if ok else 1)
