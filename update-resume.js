const fs = require('fs');
const path = require('path');

/**
 * Update resume.html with new GitHub contributions data
 */
function updateResumeContributions() {
  const dataFile = path.join(__dirname, 'frontend', 'github-contributions-data.js');
  const resumeFile = path.join(__dirname, 'frontend', 'resume.html');

  // Check if data file exists
  if (!fs.existsSync(dataFile)) {
    console.error('❌ Data file not found:', dataFile);
    return false;
  }

  try {
    // Read the data file
    const dataContent = fs.readFileSync(dataFile, 'utf8');

    // Extract the array from the data file
    // Look for the return statement with array
    const arrayMatch = dataContent.match(/return \[([\s\S]*?)\];/);
    if (!arrayMatch) {
      console.error('❌ Could not extract data array from generated file');
      return false;
    }

    const newData = arrayMatch[1].trim();

    // Read the resume file
    let resumeContent = fs.readFileSync(resumeFile, 'utf8');

    // Find and replace the getStaticContributions function
    // Look for the function and its return statement
    const functionRegex = /function getStaticContributions\(\) \{\s*return \[[\s\S]*?\];\s*\}/;

    if (!functionRegex.test(resumeContent)) {
      console.error('❌ Could not find getStaticContributions function in resume.html');
      return false;
    }

    // Create the new function content
    const newFunction = `function getStaticContributions() {
            return [${newData}];
        }`;

    // Replace the old function with the new one
    resumeContent = resumeContent.replace(functionRegex, newFunction);

    // Write back to resume file
    fs.writeFileSync(resumeFile, resumeContent, 'utf8');

    console.log('✅ Resume updated successfully with new contributions data');
    return true;

  } catch (error) {
    console.error('❌ Error updating resume:', error.message);
    return false;
  }
}

if (require.main === module) {
  const success = updateResumeContributions();
  if (!success) {
    process.exit(1);
  }
}

module.exports = { updateResumeContributions };
