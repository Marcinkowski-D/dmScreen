import importlib.metadata
import re
import requests

def check_for_update(package_name: str, github_repo: str, branch: str = "main"):
    """
    Compare the currently installed Git version of a package with the latest commit on GitHub.

    Args:
        package_name: The installed package name (e.g., "dmScreen")
        github_repo: The GitHub repo in the format "user/repo" (e.g., "youruser/dmScreen")
        branch: The branch to compare against (default: "main")
    """
    try:
        # Get installed version
        version_str = importlib.metadata.version(package_name)
        match = re.search(r'\+g([0-9a-f]+)', version_str)
        if not match:
            print(f"⚠️  Cannot determine commit hash from version string: {version_str}")
            return

        local_hash = match.group(1)
        print(f"📦 Installed version: {version_str} (commit {local_hash})")

        # Get latest commit hash from GitHub
        url = f"https://api.github.com/repos/{github_repo}/commits/{branch}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        latest_hash = response.json()["sha"][:len(local_hash)]
        print(f"🌐 Latest commit on GitHub: {latest_hash}")

        # Compare hashes
        if local_hash == latest_hash:
            print("✅ You are running the latest version.")
        else:
            print("🚨 A newer version is available on GitHub!")
    except Exception as e:
        print(f"❌ Failed to check for updates: {e}")
