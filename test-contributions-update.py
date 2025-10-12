#!/usr/bin/env python3
"""
Test script for GitHub contributions automation
Usage: python test-contributions-update.py
"""

import os
import json
import httpx
from datetime import datetime
import re

def test_contributions_update():
    """Test the contributions update process"""

    # Get GitHub token
    github_token = os.getenv('GITHUB_TOKEN') or os.getenv('PERSONAL_ACCESS_TOKEN')
    if not github_token:
        print('❌ GitHub token not configured. Set GITHUB_TOKEN environment variable.')
        return False

    print('🔄 Testing GitHub contributions update...')

    # GitHub GraphQL query
    query = '''
    query {
        user(login: "murderszn") {
            contributionsCollection {
                contributionCalendar {
                    totalContributions
                    weeks {
                        contributionDays {
                            contributionCount
                            date
                        }
                    }
                }
            }
        }
    }'''

    try:
        # Make GraphQL request
        response = httpx.post(
            'https://api.github.com/graphql',
            headers={
                'Authorization': f'Bearer {github_token}',
                'Content-Type': 'application/json'
            },
            json={'query': query}
        )

        if response.status_code != 200:
            print(f'❌ GitHub API error: {response.status_code}')
            return False

        data = response.json()
        if 'errors' in data:
            print(f'❌ GraphQL errors: {data["errors"]}')
            return False

        # Extract contributions data
        weeks = data['data']['user']['contributionsCollection']['contributionCalendar']['weeks']
        contributions = []
        for week in weeks:
            for day in week['contributionDays']:
                contributions.append({
                    'date': day['date'],
                    'count': day['contributionCount']
                })

        total_contributions = sum(c['count'] for c in contributions)

        print(f'✅ Successfully fetched {len(contributions)} days of data')
        print(f'📊 Total contributions: {total_contributions}')

        # Create JavaScript data file
        js_content = f'// Static GitHub contributions data (fetched {datetime.utcnow().strftime("%Y-%m-%d")})\n'
        js_content += 'function getStaticContributions() {\n'
        js_content += f'    return {json.dumps(contributions, indent=12)};\n'
        js_content += '}\n'

        # Write to frontend data file
        frontend_dir = 'frontend'
        os.makedirs(frontend_dir, exist_ok=True)
        data_file = os.path.join(frontend_dir, 'github-contributions-data.js')
        with open(data_file, 'w') as f:
            f.write(js_content)

        print(f'💾 Updated {data_file}')

        # Update resume.html
        resume_file = os.path.join(frontend_dir, 'resume.html')
        with open(resume_file, 'r') as f:
            resume_content = f.read()

        # Find and replace the getStaticContributions function
        pattern = r'function getStaticContributions\(\) \{\s*return \[[\s\S]*?\];\s*\}'
        new_function = f'function getStaticContributions() {{\n            return {json.dumps(contributions, indent=12)};\n        }}'

        if re.search(pattern, resume_content):
            resume_content = re.sub(pattern, new_function, resume_content)
            with open(resume_file, 'w') as f:
                f.write(resume_content)
            print(f'🔄 Updated {resume_file}')
        else:
            print('⚠️  Could not find getStaticContributions function in resume.html')

        print(f'🎉 Contributions update test completed successfully!')
        print(f'   - {total_contributions} total contributions')
        print(f'   - {len(contributions)} days processed')
        print(f'   - Files updated: {data_file}, {resume_file}')

        return True

    except Exception as e:
        print(f'❌ Error during test: {e}')
        return False

if __name__ == '__main__':
    success = test_contributions_update()
    exit(0 if success else 1)

