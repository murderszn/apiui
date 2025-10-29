#!/usr/bin/env node

/**
 * Fetch GitHub contributions for a user and generate static data for the resume
 * Usage: node fetch-github-contributions.js [username]
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

// GitHub username from command line or default
const username = process.argv[2] || 'murderszn';

// GraphQL query for contributions
const query = `
query {
    user(login: "${username}") {
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
}`;

console.log(`Fetching GitHub contributions for ${username}...`);

// Make request to GitHub GraphQL API
const postData = JSON.stringify({ query });

const options = {
    hostname: 'api.github.com',
    port: 443,
    path: '/graphql',
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData),
        'User-Agent': 'GitHub-Contributions-Fetcher',
        'Authorization': `Bearer ${process.env.GITHUB_TOKEN}`
    }
};

const req = https.request(options, (res) => {
    let data = '';

    res.on('data', (chunk) => {
        data += chunk;
    });

    res.on('end', () => {
        try {
            console.log('Raw response:', data.substring(0, 500)); // Debug first 500 chars
            const response = JSON.parse(data);

            if (response.errors) {
                console.error('GraphQL errors:', response.errors);
                return;
            }

            if (!response.data) {
                console.error('No data in response:', response);
                return;
            }

            if (!response.data.user) {
                console.error('No user data in response:', response.data);
                return;
            }

            const contributions = response.data.user.contributionsCollection.contributionCalendar.weeks
                .flatMap(week => week.contributionDays.map(day => ({
                    date: day.date,
                    count: day.contributionCount
                })));

            const totalContributions = contributions.reduce((sum, c) => sum + c.count, 0);

            // Generate JavaScript code snippet
            const jsCode = `// Static GitHub contributions data (fetched ${new Date().toISOString().split('T')[0]})
        function getStaticContributions() {
            return ${JSON.stringify(contributions, null, 12)};
        }`;

            console.log(`✅ Successfully fetched ${contributions.length} days of data`);
            console.log(`📊 Total contributions: ${totalContributions}`);
            console.log(`📅 Date range: ${contributions[0].date} to ${contributions[contributions.length - 1].date}`);

            // Save to file
            const outputPath = path.join(__dirname, 'frontend', 'github-contributions-data.js');
            fs.writeFileSync(outputPath, jsCode, 'utf8');

            console.log(`💾 Saved to ${outputPath}`);
            console.log(`📝 Copy the getStaticContributions() function into your resume.html`);

        } catch (error) {
            console.error('Error parsing response:', error);
            console.error('Raw response data:', data);
        }
    });
});

req.on('error', (e) => {
    console.error('Request failed:', e.message);
    console.log('\n💡 To use this script:');
    console.log('1. Get a GitHub Personal Access Token: https://github.com/settings/tokens');
    console.log('2. Set GITHUB_TOKEN environment variable: export GITHUB_TOKEN=your_token_here');
    console.log('3. Run: node fetch-github-contributions.js [username]');
});

req.write(postData);
req.end();
