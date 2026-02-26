#!/usr/bin/env python3
"""Discover Nano AI services on GitHub and update README.md."""

import os
import re
import time
import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
README_PATH = os.path.join(os.path.dirname(__file__), "..", "README.md")
MARKER_START = "<!-- NANO_LIST_START -->"
MARKER_END = "<!-- NANO_LIST_END -->"
MIN_STARS = 1000
API_BASE = "https://api.github.com"

# Search queries: "nano" combined with AI-related topics and direct project names
SEARCH_QUERIES = [
    "nano in:name topic:ai",
    "nano in:name topic:machine-learning",
    "nano in:name topic:llm",
    "nano in:name topic:deep-learning",
    "nano in:name topic:gpt",
    "nano in:name topic:chatbot",
    "nano in:name topic:nlp",
    "nano in:name topic:agent",
    "nano in:name topic:neural-network",
    "nano in:name topic:transformer",
    # Direct well-known project name searches
    "nanoGPT",
    "nanochat",
    "nanobot",
    "nanobrowser",
    "nanocoder",
    "nanoflow",
    "nanotron",
]


def get_headers():
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def search_repos(query):
    """Search GitHub for repositories matching the query with stars >= MIN_STARS."""
    params = {
        "q": f"{query} stars:>={MIN_STARS}",
        "sort": "stars",
        "order": "desc",
        "per_page": 100,
    }
    resp = requests.get(f"{API_BASE}/search/repositories", headers=get_headers(), params=params)
    if resp.status_code == 403:
        print(f"Rate limited on query: {query}, skipping...")
        return []
    resp.raise_for_status()
    return resp.json().get("items", [])


def parse_existing_entries(readme_content):
    """Extract existing GitHub URLs from the README table."""
    urls = set()
    pattern = re.compile(r"https://github\.com/[\w\-\.]+/[\w\-\.]+")
    start_idx = readme_content.find(MARKER_START)
    end_idx = readme_content.find(MARKER_END)
    if start_idx == -1 or end_idx == -1:
        return urls
    section = readme_content[start_idx:end_idx]
    for match in pattern.finditer(section):
        urls.add(match.group().lower().rstrip("/"))
    return urls


def build_table_row(repo):
    """Build a markdown table row for a repository."""
    name = repo["name"]
    url = repo["html_url"]
    description = (repo["description"] or "").replace("|", "-").strip()
    if len(description) > 100:
        description = description[:97] + "..."
    stars = repo["stargazers_count"]
    return f"| [{name}]({url}) | {description} | {stars} |"


def parse_table_rows(readme_content):
    """Parse existing table rows from README between markers."""
    start_idx = readme_content.find(MARKER_START)
    end_idx = readme_content.find(MARKER_END)
    if start_idx == -1 or end_idx == -1:
        return []
    section = readme_content[start_idx + len(MARKER_START):end_idx].strip()
    lines = section.split("\n")
    rows = []
    for line in lines:
        line = line.strip()
        # Skip header and separator lines
        if line.startswith("| Name") or line.startswith("|---") or not line.startswith("|"):
            continue
        rows.append(line)
    return rows


def extract_stars_from_row(row):
    """Extract the stars number from a table row for sorting."""
    parts = row.split("|")
    if len(parts) >= 4:
        stars_str = parts[3].strip().replace(",", "")
        try:
            return int(stars_str)
        except ValueError:
            return 0
    return 0


def update_row_stars(row, repos_by_url):
    """Update stars count in an existing row if we have fresh data."""
    url_match = re.search(r"https://github\.com/[\w\-\.]+/[\w\-\.]+", row)
    if url_match:
        url = url_match.group().lower().rstrip("/")
        if url in repos_by_url:
            repo = repos_by_url[url]
            new_stars = repo["stargazers_count"]
            # Replace the stars column
            parts = row.split("|")
            if len(parts) >= 5:
                parts[3] = f" {new_stars} "
                return "|".join(parts)
    return row


def set_github_output(key, value):
    """Set a GitHub Actions output variable."""
    output_file = os.environ.get("GITHUB_OUTPUT", "")
    if output_file:
        with open(output_file, "a") as f:
            if "\n" in str(value):
                f.write(f"{key}<<EOF\n{value}\nEOF\n")
            else:
                f.write(f"{key}={value}\n")


def main():
    # Read current README
    readme_path = os.path.normpath(README_PATH)
    with open(readme_path, "r") as f:
        readme_content = f.read()

    existing_urls = parse_existing_entries(readme_content)
    existing_rows = parse_table_rows(readme_content)
    print(f"Found {len(existing_urls)} existing entries in README")

    # Search GitHub for nano AI repos
    all_repos = {}
    for query in SEARCH_QUERIES:
        print(f"Searching: {query}")
        repos = search_repos(query)
        for repo in repos:
            full_name = repo["full_name"].lower()
            if full_name not in all_repos:
                all_repos[full_name] = repo
        # Respect rate limit
        time.sleep(1)

    print(f"Found {len(all_repos)} total unique repos across all queries")

    # Filter: exclude forks, archived, and already-listed repos
    new_repos = []
    repos_by_url = {}
    for full_name, repo in all_repos.items():
        url = repo["html_url"].lower().rstrip("/")
        repos_by_url[url] = repo
        if repo.get("fork"):
            continue
        if repo.get("archived"):
            continue
        if url in existing_urls:
            continue
        new_repos.append(repo)

    # Sort new repos by stars descending
    new_repos.sort(key=lambda r: r["stargazers_count"], reverse=True)

    print(f"Found {len(new_repos)} new repos to add")
    for repo in new_repos:
        print(f"  - {repo['full_name']} ({repo['stargazers_count']} stars)")

    # Update existing rows with fresh star counts
    updated_rows = [update_row_stars(row, repos_by_url) for row in existing_rows]

    # Build new rows
    new_rows = [build_table_row(repo) for repo in new_repos]

    # Combine all rows and sort by stars descending
    all_rows = updated_rows + new_rows
    all_rows.sort(key=extract_stars_from_row, reverse=True)

    # Build new table section
    table_header = "| Name | Description | Stars |\n|------|-------------|-------|\n"
    table_body = "\n".join(all_rows)
    new_section = f"{MARKER_START}\n{table_header}{table_body}\n{MARKER_END}"

    # Replace section in README
    start_idx = readme_content.find(MARKER_START)
    end_idx = readme_content.find(MARKER_END) + len(MARKER_END)
    new_readme = readme_content[:start_idx] + new_section + readme_content[end_idx:]

    # Write updated README
    with open(readme_path, "w") as f:
        f.write(new_readme)

    print(f"\nREADME updated with {len(new_repos)} new entries")

    # Set GitHub Actions outputs
    set_github_output("new_count", str(len(new_repos)))
    new_services_list = "\n".join(
        f"- [{r['full_name']}]({r['html_url']}) ({r['stargazers_count']} stars)"
        for r in new_repos
    )
    set_github_output("new_services", new_services_list if new_services_list else "None")


if __name__ == "__main__":
    main()
