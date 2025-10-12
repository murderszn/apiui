# GitHub Contributions Calendar

This project includes a beautiful pink-themed GitHub-style contributions calendar for your resume.

## 🎨 Features

- **Pink Theme**: Matches your site's aesthetic with a gradient from light pink to deep pink
- **Interactive Tooltips**: Hover over any day to see contribution count and date
- **Statistics Dashboard**: Shows total contributions, daily average, busiest day, and active days
- **Responsive Design**: Works on all screen sizes
- **Static Data**: No API calls needed - data is embedded directly in the page

## 📊 Current Implementation

The calendar currently uses realistic static data based on your GitHub activity patterns. The data represents:
- **High activity periods**: Major project development (85% contribution rate)
- **Medium activity periods**: Maintenance and updates (75% contribution rate)
- **Low activity periods**: Code review and planning (60% contribution rate)
- **Weekend activity**: Occasional contributions (30% chance)

## 🔄 Updating with Real Data

To fetch your actual GitHub contribution data, you have two options:

### Option 1: Use the Fetch Script (Recommended)

1. **Get a GitHub Personal Access Token**:
   - Go to [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens)
   - Create a new token with `read:user` scope
   - Copy the token

2. **Set the environment variable**:
   ```bash
   export GITHUB_TOKEN=your_token_here
   ```

3. **Run the fetch script**:
   ```bash
   node fetch-github-contributions.js murderszn
   ```

4. **Update the resume**:
   - The script will generate a new `getStaticContributions()` function
   - Copy the function from `frontend/github-contributions-data.js`
   - Replace the existing function in `resume.html`

### Option 2: Manual GraphQL Query

If you prefer to do it manually:

1. Go to [GitHub's GraphQL Explorer](https://docs.github.com/en/graphql/overview/explorer)
2. Use this query:
   ```graphql
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
   }
   ```

3. Copy the `contributionCalendar.weeks` data
4. Format it into the JavaScript array format

## 🎯 Customization

### Adjusting Activity Patterns

Edit the `patterns` object in `getStaticContributions()` to match your actual work patterns:

```javascript
const patterns = {
    highActivity: [/* months with heavy coding */],
    mediumActivity: [/* months with regular coding */],
    lowActivity: [/* months with light coding */],
    variableActivity: [/* months with mixed activity */]
};
```

### Color Scheme

The pink gradient is defined in CSS:
```css
.contribution-day[data-level="1"] { background-color: #fce7f3; } /* Light pink */
.contribution-day[data-level="2"] { background-color: #fbcfe8; }
.contribution-day[data-level="3"] { background-color: #f9a8d4; }
.contribution-day[data-level="4"] { background-color: #f472b6; }
.contribution-day[data-level="5"] { background-color: #ec4899; } /* Deep pink */
```

## 🚀 Performance Benefits

- **No API calls**: Instant loading
- **No CORS issues**: Works in any environment
- **No rate limits**: Never gets blocked
- **Privacy friendly**: Data stays on your site

## 📱 Responsive Design

The calendar automatically adapts to different screen sizes:
- **Desktop**: Full calendar with all features
- **Mobile**: Horizontal scroll with touch-friendly interactions

## 🎨 Integration

The calendar is fully integrated into your existing resume design:
- Uses your `resume-card` styling
- Matches your pink theme (`--hub-pink`)
- Includes your Pixelify Sans font for statistics
- Positioned between "About" and "Skills" sections
